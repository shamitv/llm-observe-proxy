from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urljoin

import httpx

HF_ROUTER_MODELS_API = "https://router.huggingface.co/v1/models"
OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"
CATALOG_SOURCES = {"huggingface-router", "openrouter"}
DEFAULT_CATALOG_LIMIT = 25
MAX_CATALOG_LIMIT = 100
OPENROUTER_PER_TOKEN_MULTIPLIER = Decimal("1000000")


class CatalogFetchError(ValueError):
    pass


@dataclass(frozen=True)
class PricingCatalogRow:
    source: str
    provider_slug: str
    model: str
    display_name: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal | None = None
    aliases: tuple[str, ...] = ()
    source_url: str = ""
    checked_at: str = ""
    notes: str = ""
    row_kind: str = "base"
    external_provider: str | None = None
    context_length: int | None = None
    supports_tools: bool | None = None

    @property
    def key(self) -> str:
        return f"{self.provider_slug}:{self.model}"


async def fetch_catalog_rows(
    client: httpx.AsyncClient,
    *,
    source: str,
    search: str = "",
    limit: int = DEFAULT_CATALOG_LIMIT,
    include_base_rows: bool = True,
    include_provider_rows: bool = True,
    api_key: str | None = None,
) -> list[PricingCatalogRow]:
    resolved_source = _source(source)
    model_limit = _limit(limit)
    checked_at = datetime.now(UTC).date().isoformat()
    if resolved_source == "huggingface-router":
        payload = await _get_json(client, HF_ROUTER_MODELS_API, api_key=api_key)
        return normalize_hf_catalog(
            payload,
            search=search,
            limit=model_limit,
            include_base_rows=include_base_rows,
            include_provider_rows=include_provider_rows,
            checked_at=checked_at,
        )

    models_payload = await _get_json(client, OPENROUTER_MODELS_API, api_key=api_key)
    model_items = _filtered_items(_data_list(models_payload), search)[:model_limit]
    endpoint_payloads: dict[str, object] = {}
    if include_provider_rows:
        for item in model_items:
            if not isinstance(item, dict):
                continue
            model_id = _text(item.get("id"))
            if not model_id:
                continue
            endpoint_url = _openrouter_endpoint_url(item, model_id)
            try:
                endpoint_payloads[model_id] = await _get_json(
                    client,
                    endpoint_url,
                    api_key=api_key,
                )
            except CatalogFetchError:
                continue
    return normalize_openrouter_catalog(
        {"data": model_items},
        endpoint_payloads=endpoint_payloads,
        search="",
        limit=model_limit,
        include_base_rows=include_base_rows,
        include_provider_rows=include_provider_rows,
        checked_at=checked_at,
    )


def normalize_hf_catalog(
    payload: object,
    *,
    search: str = "",
    limit: int = DEFAULT_CATALOG_LIMIT,
    include_base_rows: bool = True,
    include_provider_rows: bool = True,
    checked_at: str | None = None,
) -> list[PricingCatalogRow]:
    rows: list[PricingCatalogRow] = []
    model_items = _filtered_items(_data_list(payload), search)[: _limit(limit)]
    checked = checked_at or datetime.now(UTC).date().isoformat()
    for item in model_items:
        if not isinstance(item, dict):
            continue
        model_id = _text(item.get("id"))
        if not model_id:
            continue
        provider_entries = [
            entry for entry in _providers(item) if _hf_rates(entry) is not None
        ]
        if include_base_rows and provider_entries:
            cheapest = min(
                provider_entries,
                key=lambda entry: (
                    (_hf_rates(entry) or (Decimal("0"), Decimal("0")))[0]
                    + (_hf_rates(entry) or (Decimal("0"), Decimal("0")))[1],
                    _text(entry.get("provider")),
                ),
            )
            rates = _hf_rates(cheapest)
            if rates is not None:
                provider_name = _text(cheapest.get("provider"))
                rows.append(
                    PricingCatalogRow(
                        source="huggingface-router",
                        provider_slug="huggingface-router",
                        model=model_id,
                        display_name=f"{model_id} (HF Router)",
                        aliases=_dedupe_aliases(_lower_alias(model_id)),
                        input_usd_per_million=rates[0],
                        output_usd_per_million=rates[1],
                        source_url=_hf_model_url(model_id),
                        checked_at=checked,
                        notes=_notes(
                            f"HF Router base row from listed provider {provider_name}.",
                            _hf_provider_note(cheapest),
                        ),
                        row_kind="base",
                        external_provider=provider_name,
                        context_length=_int_or_none(cheapest.get("context_length")),
                        supports_tools=_bool_or_none(cheapest.get("supports_tools")),
                    )
                )
        if not include_provider_rows:
            continue
        for entry in provider_entries:
            provider_name = _text(entry.get("provider"))
            rates = _hf_rates(entry)
            if not provider_name or rates is None:
                continue
            provider_model = f"{model_id}:{provider_name}"
            rows.append(
                PricingCatalogRow(
                    source="huggingface-router",
                    provider_slug="huggingface-router",
                    model=provider_model,
                    display_name=f"{model_id} ({provider_name})",
                    aliases=_dedupe_aliases(provider_model, _lower_alias(provider_model)),
                    input_usd_per_million=rates[0],
                    output_usd_per_million=rates[1],
                    source_url=_hf_model_url(model_id),
                    checked_at=checked,
                    notes=_notes("HF Router provider-specific row.", _hf_provider_note(entry)),
                    row_kind="provider",
                    external_provider=provider_name,
                    context_length=_int_or_none(entry.get("context_length")),
                    supports_tools=_bool_or_none(entry.get("supports_tools")),
                )
            )
    return rows


def normalize_openrouter_catalog(
    models_payload: object,
    *,
    endpoint_payloads: dict[str, object] | None = None,
    search: str = "",
    limit: int = DEFAULT_CATALOG_LIMIT,
    include_base_rows: bool = True,
    include_provider_rows: bool = True,
    checked_at: str | None = None,
) -> list[PricingCatalogRow]:
    rows: list[PricingCatalogRow] = []
    endpoints = endpoint_payloads or {}
    model_items = _filtered_items(_data_list(models_payload), search)[: _limit(limit)]
    checked = checked_at or datetime.now(UTC).date().isoformat()
    for item in model_items:
        if not isinstance(item, dict):
            continue
        model_id = _text(item.get("id"))
        if not model_id:
            continue
        if include_base_rows:
            rates = _openrouter_rates(item.get("pricing"))
            if rates is not None:
                rows.append(
                    PricingCatalogRow(
                        source="openrouter",
                        provider_slug="openrouter",
                        model=model_id,
                        display_name=_text(item.get("name")) or f"{model_id} (OpenRouter)",
                        aliases=_dedupe_aliases(
                            _text(item.get("canonical_slug")),
                            _lower_alias(model_id),
                        ),
                        input_usd_per_million=rates[0],
                        cached_input_usd_per_million=rates[2],
                        output_usd_per_million=rates[1],
                        source_url=OPENROUTER_MODELS_API,
                        checked_at=checked,
                        notes=_notes(
                            "OpenRouter base model row from /api/v1/models.",
                            _openrouter_price_note(item.get("pricing")),
                            _context_note(item.get("context_length")),
                            _tools_note(item.get("supported_parameters")),
                        ),
                        row_kind="base",
                        context_length=_int_or_none(item.get("context_length")),
                        supports_tools=_supports_tools(item.get("supported_parameters")),
                    )
                )
        if not include_provider_rows:
            continue
        endpoint_payload = endpoints.get(model_id)
        if endpoint_payload is None:
            continue
        for endpoint in _openrouter_endpoints(endpoint_payload):
            if not isinstance(endpoint, dict):
                continue
            tag = _text(endpoint.get("tag"))
            if not tag:
                continue
            rates = _openrouter_rates(endpoint.get("pricing"))
            if rates is None:
                continue
            endpoint_model = f"{model_id}@{tag}"
            provider_name = _text(endpoint.get("provider_name"))
            rows.append(
                PricingCatalogRow(
                    source="openrouter",
                    provider_slug="openrouter",
                    model=endpoint_model,
                    display_name=f"{_text(item.get('name')) or model_id} ({provider_name or tag})",
                    aliases=_dedupe_aliases(endpoint_model, f"{model_id}:{tag}"),
                    input_usd_per_million=rates[0],
                    cached_input_usd_per_million=rates[2],
                    output_usd_per_million=rates[1],
                    source_url=_openrouter_endpoint_url(item, model_id),
                    checked_at=checked,
                    notes=_notes(
                        "OpenRouter provider endpoint row.",
                        _openrouter_endpoint_note(endpoint),
                        _openrouter_price_note(endpoint.get("pricing")),
                    ),
                    row_kind="provider",
                    external_provider=provider_name or tag,
                    context_length=_int_or_none(endpoint.get("context_length")),
                    supports_tools=_supports_tools(endpoint.get("supported_parameters")),
                )
            )
    return rows


def _source(value: str) -> str:
    source = value.strip()
    if source not in CATALOG_SOURCES:
        raise CatalogFetchError("Unsupported pricing catalog source.")
    return source


def _limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_CATALOG_LIMIT
    return max(1, min(parsed, MAX_CATALOG_LIMIT))


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    api_key: str | None,
) -> object:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = await client.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogFetchError(f"Could not fetch pricing catalog from {url}: {exc}") from exc


def _data_list(payload: object) -> list[object]:
    if isinstance(payload, dict):
        data = payload.get("data")
        return data if isinstance(data, list) else []
    return payload if isinstance(payload, list) else []


def _filtered_items(items: list[object], search: str) -> list[object]:
    needle = search.strip().lower()
    if not needle:
        return items
    return [item for item in items if needle in _search_text(item)]


def _search_text(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    providers = " ".join(_text(entry.get("provider")) for entry in _providers(item))
    return " ".join(
        part
        for part in (
            _text(item.get("id")),
            _text(item.get("name")),
            _text(item.get("canonical_slug")),
            _text(item.get("owned_by")),
            providers,
        )
        if part
    ).lower()


def _providers(item: dict[str, object]) -> list[dict[str, object]]:
    providers = item.get("providers")
    return [entry for entry in providers if isinstance(entry, dict)] if isinstance(
        providers, list
    ) else []


def _hf_rates(entry: dict[str, object]) -> tuple[Decimal, Decimal] | None:
    pricing = entry.get("pricing")
    if not isinstance(pricing, dict):
        return None
    input_rate = _decimal(pricing.get("input"))
    output_rate = _decimal(pricing.get("output"))
    if input_rate is None or output_rate is None:
        return None
    return input_rate, output_rate


def _openrouter_rates(pricing: object) -> tuple[Decimal, Decimal, Decimal | None] | None:
    if not isinstance(pricing, dict):
        return None
    input_rate = _decimal(pricing.get("prompt"), multiplier=OPENROUTER_PER_TOKEN_MULTIPLIER)
    output_rate = _decimal(
        pricing.get("completion"),
        multiplier=OPENROUTER_PER_TOKEN_MULTIPLIER,
    )
    cached_rate = _decimal(
        pricing.get("input_cache_read")
        or pricing.get("cache_read")
        or pricing.get("prompt_cache_read"),
        multiplier=OPENROUTER_PER_TOKEN_MULTIPLIER,
    )
    if input_rate is None or output_rate is None:
        return None
    return input_rate, output_rate, cached_rate


def _decimal(value: object, *, multiplier: Decimal = Decimal("1")) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = Decimal(str(value).strip()) * multiplier
    except (InvalidOperation, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _openrouter_endpoint_url(item: dict[str, object], model_id: str) -> str:
    links = item.get("links")
    if isinstance(links, dict):
        details = _text(links.get("details"))
        if details:
            return urljoin("https://openrouter.ai", details)
    return f"{OPENROUTER_MODELS_API}/{model_id}/endpoints"


def _openrouter_endpoints(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    endpoints = data.get("endpoints")
    return endpoints if isinstance(endpoints, list) else []


def _hf_model_url(model_id: str) -> str:
    return f"{HF_ROUTER_MODELS_API}/{quote(model_id, safe='/')}"


def _openrouter_price_note(pricing: object) -> str:
    if not isinstance(pricing, dict):
        return ""
    ignored = []
    for key in ("request", "image", "input_cache_write", "discount"):
        value = pricing.get(key)
        if value in (None, "", "0", 0):
            continue
        ignored.append(f"{key}={value}")
    if not ignored:
        return ""
    return f"Ignored OpenRouter non-modeled pricing fields: {', '.join(ignored)}."


def _openrouter_endpoint_note(endpoint: dict[str, object]) -> str:
    parts = [
        f"provider={_text(endpoint.get('provider_name')) or '-'}",
        f"tag={_text(endpoint.get('tag')) or '-'}",
    ]
    context = _int_or_none(endpoint.get("context_length"))
    if context is not None:
        parts.append(f"context={context}")
    quantization = _text(endpoint.get("quantization"))
    if quantization:
        parts.append(f"quantization={quantization}")
    return "; ".join(parts) + "."


def _hf_provider_note(entry: dict[str, object]) -> str:
    parts = [
        f"provider={_text(entry.get('provider')) or '-'}",
        f"status={_text(entry.get('status')) or '-'}",
    ]
    context = _int_or_none(entry.get("context_length"))
    if context is not None:
        parts.append(f"context={context}")
    tools = _bool_or_none(entry.get("supports_tools"))
    if tools is not None:
        parts.append(f"supports_tools={str(tools).lower()}")
    return "; ".join(parts) + "."


def _context_note(value: object) -> str:
    context = _int_or_none(value)
    return f"context={context}." if context is not None else ""


def _tools_note(value: object) -> str:
    tools = _supports_tools(value)
    return f"supports_tools={str(tools).lower()}." if tools is not None else ""


def _supports_tools(value: object) -> bool | None:
    if not isinstance(value, list):
        return None
    return "tools" in {str(item) for item in value}


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _lower_alias(value: str) -> str:
    lowered = value.lower()
    return lowered if lowered != value else ""


def _dedupe_aliases(*values: str) -> tuple[str, ...]:
    aliases: list[str] = []
    for value in values:
        alias = value.strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


def _notes(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())
