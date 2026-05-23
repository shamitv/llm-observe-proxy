from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Text, and_, cast, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, defer

from llm_observe_proxy.capture import (
    ExtractedTokenUsage,
    decode_json_bytes,
    decode_sse_json_events,
    extract_model,
    extract_stream_token_usage,
    extract_token_usage,
)
from llm_observe_proxy.config import normalize_provider_url
from llm_observe_proxy.database import ModelPrice, ModelPriceTier, ModelProvider, RequestRecord

TOKENS_PER_MILLION = Decimal("1000000")
HISTORICAL_CACHED_COST_BACKFILL = "cached-input-v0.4"


@dataclass(frozen=True)
class CostEstimate:
    provider_slug: str | None
    provider_name: str | None
    billing_model: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    cache_write_input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    input_cost_usd: Decimal | None = None
    cached_input_cost_usd: Decimal | None = None
    output_cost_usd: Decimal | None = None
    total_cost_usd: Decimal | None = None
    snapshot: dict[str, object] | None = None


@dataclass(frozen=True)
class RunCostEstimate:
    provider_slug: str
    provider_name: str
    currency: str
    model: str
    display_name: str | None
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal | None
    output_usd_per_million: Decimal
    mixed_tiers: bool
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: Decimal
    cached_input_cost_usd: Decimal | None
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    included_request_count: int
    missing_usage_request_count: int
    notes: str | None = None


@dataclass(frozen=True)
class _ResolvedRates:
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal | None
    output_usd_per_million: Decimal
    source_kind: str
    tier: ModelPriceTier | None = None

    @property
    def source_url(self) -> str | None:
        return self.tier.source_url if self.tier else None

    @property
    def checked_at(self) -> str | None:
        return self.tier.checked_at if self.tier else None

    @property
    def release_date(self) -> str | None:
        return self.tier.release_date if self.tier else None

    @property
    def notes(self) -> str | None:
        return self.tier.notes if self.tier else None


def estimate_cost(
    session: Session,
    *,
    usage: ExtractedTokenUsage,
    billing_model: str | None,
    provider_slug: str | None = None,
    upstream_base_url: str | None = None,
) -> CostEstimate:
    resolved_model = billing_model.strip() if billing_model else None
    provider = _resolve_provider(session, provider_slug, upstream_base_url)
    base = CostEstimate(
        provider_slug=provider.slug if provider else None,
        provider_name=provider.name if provider else None,
        billing_model=resolved_model,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_input_tokens=usage.cache_write_input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    if provider is None or resolved_model is None:
        return base

    price = _find_model_price(session, provider.slug, resolved_model)
    if price is None or usage.input_tokens is None or usage.output_tokens is None:
        return base

    rates = _resolve_rates(price, usage.input_tokens)
    input_cost, cached_input_cost, uncached_input_tokens, cache_pricing = _input_cost(
        usage.input_tokens,
        usage.cached_input_tokens,
        input_rate=rates.input_usd_per_million,
        cached_input_rate=rates.cached_input_usd_per_million,
    )
    output_cost = _token_cost(usage.output_tokens, rates.output_usd_per_million)
    total_cost = input_cost + output_cost
    snapshot = {
        "provider_slug": provider.slug,
        "provider_name": provider.name,
        "currency": provider.currency,
        "billing_model": resolved_model,
        "matched_model": price.model,
        "display_name": price.display_name,
        "input_usd_per_million": str(rates.input_usd_per_million),
        "cached_input_usd_per_million": (
            str(rates.cached_input_usd_per_million)
            if rates.cached_input_usd_per_million is not None
            else None
        ),
        "output_usd_per_million": str(rates.output_usd_per_million),
        "cached_input_tokens": usage.cached_input_tokens,
        "cache_write_input_tokens": usage.cache_write_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "cached_input_pricing": cache_pricing,
        "pricing_source_kind": rates.source_kind,
        "source_url": rates.source_url or price.source_url,
        "checked_at": rates.checked_at or price.checked_at,
        "release_date": rates.release_date or price.release_date,
        "source": rates.notes or price.notes,
    }
    if rates.tier is not None:
        snapshot.update(
            {
                "tier_id": rates.tier.id,
                "tier_label": rates.tier.label,
                "tier_min_input_tokens": rates.tier.min_input_tokens,
                "tier_max_input_tokens": rates.tier.max_input_tokens,
            }
        )
    return CostEstimate(
        provider_slug=provider.slug,
        provider_name=provider.name,
        billing_model=resolved_model,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_input_tokens=usage.cache_write_input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        snapshot=snapshot,
    )


def estimate_run_cost(
    usages: Iterable[ExtractedTokenUsage],
    price: ModelPrice,
) -> RunCostEstimate:
    input_tokens = 0
    cached_input_tokens = 0
    cache_write_input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    input_cost = Decimal("0")
    output_cost = Decimal("0")
    cached_input_cost: Decimal | None = None
    included_request_count = 0
    missing_usage_request_count = 0
    rate_keys: set[tuple[Decimal, Decimal | None, Decimal, str, int | None]] = set()

    for usage in usages:
        if usage.input_tokens is None or usage.output_tokens is None:
            missing_usage_request_count += 1
            continue

        included_request_count += 1
        input_tokens += usage.input_tokens
        if usage.cached_input_tokens is not None:
            cached_input_tokens += min(usage.cached_input_tokens, usage.input_tokens)
        if usage.cache_write_input_tokens is not None:
            cache_write_input_tokens += usage.cache_write_input_tokens
        output_tokens += usage.output_tokens
        total_tokens += (
            usage.total_tokens
            if usage.total_tokens is not None
            else usage.input_tokens + usage.output_tokens
        )
        rates = _resolve_rates(price, usage.input_tokens)
        request_input_cost, request_cached_input_cost, _, _ = _input_cost(
            usage.input_tokens,
            usage.cached_input_tokens,
            input_rate=rates.input_usd_per_million,
            cached_input_rate=rates.cached_input_usd_per_million,
        )
        input_cost += request_input_cost
        output_cost += _token_cost(usage.output_tokens, rates.output_usd_per_million)
        if request_cached_input_cost is not None:
            cached_input_cost = (cached_input_cost or Decimal("0")) + request_cached_input_cost
        rate_keys.add(
            (
                rates.input_usd_per_million,
                rates.cached_input_usd_per_million,
                rates.output_usd_per_million,
                rates.source_kind,
                rates.tier.id if rates.tier else None,
            )
        )
    mixed_tiers = len(rate_keys) > 1
    display_rates = _display_rates(price, rate_keys)
    provider = price.provider
    return RunCostEstimate(
        provider_slug=price.provider_slug,
        provider_name=provider.name if provider else price.provider_slug,
        currency=provider.currency if provider else "USD",
        model=price.model,
        display_name=price.display_name,
        input_usd_per_million=display_rates[0],
        cached_input_usd_per_million=display_rates[1],
        output_usd_per_million=display_rates[2],
        mixed_tiers=mixed_tiers,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
        included_request_count=included_request_count,
        missing_usage_request_count=missing_usage_request_count,
        notes=price.notes,
    )


def apply_cost_estimate(record: RequestRecord, estimate: CostEstimate) -> None:
    record.billing_provider_slug = estimate.provider_slug
    record.billing_provider_name = estimate.provider_name
    record.billing_model = estimate.billing_model
    record.billing_input_tokens = estimate.input_tokens
    record.billing_cached_input_tokens = estimate.cached_input_tokens
    record.billing_output_tokens = estimate.output_tokens
    record.billing_total_tokens = estimate.total_tokens
    record.billing_input_cost_usd = estimate.input_cost_usd
    record.billing_output_cost_usd = estimate.output_cost_usd
    record.billing_total_cost_usd = estimate.total_cost_usd
    record.pricing_snapshot_json = (
        json.dumps(estimate.snapshot, ensure_ascii=False, separators=(",", ":"))
        if estimate.snapshot
        else None
    )


def backfill_historical_cached_cost_estimates(engine: Engine) -> int:
    """Reprice older cached-token rows that predate cached-input snapshots."""
    if not _request_records_table_supports_backfill(engine):
        return 0
    updated = 0
    with Session(engine) as session:
        providers = session.scalars(select(ModelProvider)).all()
        providers_by_slug = {provider.slug: provider for provider in providers}
        provider_urls = tuple(
            (provider.slug, provider.upstream_url.rstrip("/"))
            for provider in providers
            if provider.upstream_url
        )
        for candidate_filter in _backfill_candidate_filters(engine):
            records = session.scalars(
                select(RequestRecord)
                .where(candidate_filter)
                .options(
                    defer(RequestRecord.request_body),
                    defer(RequestRecord.response_body),
                    defer(RequestRecord.upstream_response_body_raw),
                )
                .execution_options(yield_per=200)
            )
            for record in records:
                provider_slug = _record_provider_slug(record, providers_by_slug, provider_urls)
                if provider_slug is None:
                    continue
                billing_model = _record_billing_model(record)
                if billing_model is None:
                    continue
                usage = _record_usage_for_backfill(record)
                if (
                    usage.input_tokens is None
                    or usage.output_tokens is None
                    or not usage.cached_input_tokens
                ):
                    continue

                estimate = estimate_cost(
                    session,
                    usage=usage,
                    billing_model=billing_model,
                    provider_slug=provider_slug,
                )
                if (
                    estimate.total_cost_usd is None
                    or estimate.snapshot is None
                    or not _should_backfill_cached_cost(record, estimate.snapshot)
                ):
                    continue

                previous_total_cost_usd = (
                    str(record.billing_total_cost_usd)
                    if record.billing_total_cost_usd is not None
                    else None
                )
                apply_cost_estimate(record, estimate)
                snapshot = dict(estimate.snapshot)
                snapshot["historical_cost_backfill"] = HISTORICAL_CACHED_COST_BACKFILL
                if previous_total_cost_usd is not None:
                    snapshot["previous_total_cost_usd"] = previous_total_cost_usd
                record.pricing_snapshot_json = json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                updated += 1
        if updated:
            session.commit()
    return updated


def _backfill_candidate_filters(engine: Engine):
    stale_snapshot = or_(
        RequestRecord.pricing_snapshot_json.is_(None),
        ~RequestRecord.pricing_snapshot_json.like('%"cached_input_pricing"%'),
        RequestRecord.pricing_snapshot_json.like('%"standard_input_rate"%'),
    )
    cached_tokens_recorded = and_(
        stale_snapshot,
        RequestRecord.billing_cached_input_tokens > 0,
    )
    if engine.dialect.name != "sqlite":
        return (cached_tokens_recorded,)

    response_body_text = cast(RequestRecord.response_body, Text)
    cached_usage_marker = or_(
        RequestRecord.billing_cached_input_tokens > 0,
        response_body_text.like('%"cached_tokens"%'),
        response_body_text.like('%"cache_read_tokens"%'),
        response_body_text.like('%"cached_input_tokens"%'),
        response_body_text.like('%"prompt_cache_hit_tokens"%'),
    )
    cached_tokens_not_recorded = or_(
        RequestRecord.billing_cached_input_tokens.is_(None),
        RequestRecord.billing_cached_input_tokens <= 0,
    )
    return (
        cached_tokens_recorded,
        and_(stale_snapshot, cached_tokens_not_recorded, cached_usage_marker),
    )


def _request_records_table_supports_backfill(engine: Engine) -> bool:
    if engine.dialect.name != "sqlite":
        return True
    inspector = inspect(engine)
    if "request_records" not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns("request_records")}
    mapped_columns = set(RequestRecord.__table__.columns.keys())
    return mapped_columns <= columns


def _resolve_provider(
    session: Session,
    provider_slug: str | None,
    upstream_base_url: str | None,
) -> ModelProvider | None:
    if provider_slug:
        return session.get(ModelProvider, provider_slug)

    try:
        normalized_url = normalize_provider_url(upstream_base_url)
    except ValueError:
        return None
    if normalized_url is None:
        return None
    return session.scalar(select(ModelProvider).where(ModelProvider.upstream_url == normalized_url))


def _record_usage_for_backfill(record: RequestRecord) -> ExtractedTokenUsage:
    response_usage = (
        extract_stream_token_usage(record.response_body)
        if record.is_stream
        else extract_token_usage(decode_json_bytes(record.response_body))
    )
    return ExtractedTokenUsage(
        input_tokens=_prefer_existing(record.billing_input_tokens, response_usage.input_tokens),
        cached_input_tokens=_prefer_existing(
            record.billing_cached_input_tokens,
            response_usage.cached_input_tokens,
        ),
        cache_write_input_tokens=response_usage.cache_write_input_tokens,
        output_tokens=_prefer_existing(record.billing_output_tokens, response_usage.output_tokens),
        total_tokens=_prefer_existing(record.billing_total_tokens, response_usage.total_tokens),
    )


def _record_provider_slug(
    record: RequestRecord,
    providers_by_slug: dict[str, ModelProvider],
    provider_urls: tuple[tuple[str, str], ...],
) -> str | None:
    if record.billing_provider_slug and record.billing_provider_slug in providers_by_slug:
        return record.billing_provider_slug
    if not record.upstream_url:
        return None
    try:
        upstream_url = normalize_provider_url(record.upstream_url)
    except ValueError:
        return None
    if upstream_url is None:
        return None
    for slug, provider_url in provider_urls:
        if upstream_url == provider_url or upstream_url.startswith(f"{provider_url}/"):
            return slug
    return None


def _record_billing_model(record: RequestRecord) -> str | None:
    for value in (
        record.billing_model,
        record.upstream_model,
        _body_model(record),
        record.model,
    ):
        if value and value.strip():
            return value.strip()
    return None


def _body_model(record: RequestRecord) -> str | None:
    if record.is_stream:
        for event in decode_sse_json_events(record.response_body):
            model = extract_model(event)
            if model:
                return model
        return None
    return extract_model(decode_json_bytes(record.response_body))


def _should_backfill_cached_cost(
    record: RequestRecord,
    new_snapshot: dict[str, object],
) -> bool:
    existing_snapshot = _decode_snapshot(record.pricing_snapshot_json)
    if existing_snapshot.get("historical_cost_backfill") == HISTORICAL_CACHED_COST_BACKFILL:
        return False
    existing_cache_pricing = existing_snapshot.get("cached_input_pricing")
    if existing_cache_pricing is None:
        return True
    if record.billing_total_cost_usd is None:
        return True
    return (
        existing_cache_pricing == "standard_input_rate"
        and new_snapshot.get("cached_input_pricing") == "cached_input_rate"
    )


def _decode_snapshot(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _prefer_existing(existing: int | None, extracted: int | None) -> int | None:
    return existing if existing is not None else extracted


def _find_model_price(session: Session, provider_slug: str, model: str) -> ModelPrice | None:
    # Fast path: exact (provider_slug, model) match
    exact = session.scalar(
        select(ModelPrice).where(
            ModelPrice.provider_slug == provider_slug,
            ModelPrice.model == model,
            ModelPrice.active.is_(True),
        )
    )
    if exact is not None:
        return exact

    # Fallback: scan aliases for all active prices of this provider
    prices = session.scalars(
        select(ModelPrice).where(
            ModelPrice.provider_slug == provider_slug,
            ModelPrice.active.is_(True),
        )
    ).all()
    for price in prices:
        if model in _price_aliases(price):
            return price
    return None


def _price_aliases(price: ModelPrice) -> tuple[str, ...]:
    if not price.aliases_json:
        return ()
    try:
        aliases = json.loads(price.aliases_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(aliases, list):
        return ()
    return tuple(alias for alias in aliases if isinstance(alias, str))


def _resolve_rates(price: ModelPrice, input_tokens: int) -> _ResolvedRates:
    tier = _matching_tier(price, input_tokens)
    if tier is None:
        return _ResolvedRates(
            input_usd_per_million=price.input_usd_per_million,
            cached_input_usd_per_million=price.cached_input_usd_per_million,
            output_usd_per_million=price.output_usd_per_million,
            source_kind="model_price",
        )
    return _ResolvedRates(
        input_usd_per_million=tier.input_usd_per_million,
        cached_input_usd_per_million=tier.cached_input_usd_per_million,
        output_usd_per_million=tier.output_usd_per_million,
        source_kind="model_price_tier",
        tier=tier,
    )


def _matching_tier(price: ModelPrice, input_tokens: int) -> ModelPriceTier | None:
    for tier in sorted(
        price.tiers,
        key=lambda item: (
            item.min_input_tokens if item.min_input_tokens is not None else 0,
            item.max_input_tokens if item.max_input_tokens is not None else 2**63 - 1,
        ),
    ):
        minimum = tier.min_input_tokens if tier.min_input_tokens is not None else 0
        if input_tokens < minimum:
            continue
        if tier.max_input_tokens is not None and input_tokens >= tier.max_input_tokens:
            continue
        return tier
    return None


def _display_rates(
    price: ModelPrice,
    rate_keys: set[tuple[Decimal, Decimal | None, Decimal, str, int | None]],
) -> tuple[Decimal, Decimal | None, Decimal]:
    if len(rate_keys) == 1:
        input_rate, cached_input_rate, output_rate, _, _ = next(iter(rate_keys))
        return input_rate, cached_input_rate, output_rate
    return (
        price.input_usd_per_million,
        price.cached_input_usd_per_million,
        price.output_usd_per_million,
    )


def _token_cost(tokens: int, usd_per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * usd_per_million) / TOKENS_PER_MILLION


def _input_cost(
    input_tokens: int,
    cached_input_tokens: int | None,
    *,
    input_rate: Decimal,
    cached_input_rate: Decimal | None,
) -> tuple[Decimal, Decimal | None, int, str]:
    cached_tokens = min(cached_input_tokens or 0, input_tokens)
    uncached_tokens = input_tokens - cached_tokens
    if cached_tokens and cached_input_rate is not None:
        uncached_cost = _token_cost(uncached_tokens, input_rate)
        cached_cost = _token_cost(cached_tokens, cached_input_rate)
        return uncached_cost + cached_cost, cached_cost, uncached_tokens, "cached_input_rate"
    input_cost = _token_cost(input_tokens, input_rate)
    if cached_tokens:
        return input_cost, None, uncached_tokens, "standard_input_rate"
    return input_cost, None, input_tokens, "not_reported"
