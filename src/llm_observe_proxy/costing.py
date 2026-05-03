from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from llm_observe_proxy.capture import ExtractedTokenUsage
from llm_observe_proxy.config import normalize_provider_url
from llm_observe_proxy.database import ModelPrice, ModelProvider, RequestRecord

TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class CostEstimate:
    provider_slug: str | None
    provider_name: str | None
    billing_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    input_cost_usd: Decimal | None = None
    output_cost_usd: Decimal | None = None
    total_cost_usd: Decimal | None = None
    snapshot: dict[str, object] | None = None


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
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    if provider is None or resolved_model is None:
        return base

    price = _find_model_price(session, provider.slug, resolved_model)
    if price is None or usage.input_tokens is None or usage.output_tokens is None:
        return base

    input_cost = _token_cost(usage.input_tokens, price.input_usd_per_million)
    output_cost = _token_cost(usage.output_tokens, price.output_usd_per_million)
    total_cost = input_cost + output_cost
    snapshot = {
        "provider_slug": provider.slug,
        "provider_name": provider.name,
        "currency": provider.currency,
        "billing_model": resolved_model,
        "matched_model": price.model,
        "display_name": price.display_name,
        "input_usd_per_million": str(price.input_usd_per_million),
        "output_usd_per_million": str(price.output_usd_per_million),
        "source": price.notes,
    }
    return CostEstimate(
        provider_slug=provider.slug,
        provider_name=provider.name,
        billing_model=resolved_model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        snapshot=snapshot,
    )


def apply_cost_estimate(record: RequestRecord, estimate: CostEstimate) -> None:
    record.billing_provider_slug = estimate.provider_slug
    record.billing_provider_name = estimate.provider_name
    record.billing_model = estimate.billing_model
    record.billing_input_tokens = estimate.input_tokens
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


def _find_model_price(session: Session, provider_slug: str, model: str) -> ModelPrice | None:
    prices = session.scalars(
        select(ModelPrice).where(
            ModelPrice.provider_slug == provider_slug,
            ModelPrice.active.is_(True),
        )
    ).all()
    for price in prices:
        if price.model == model or model in _price_aliases(price):
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


def _token_cost(tokens: int, usd_per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * usd_per_million) / TOKENS_PER_MILLION
