from __future__ import annotations

from typing import Any

from llm_observe_proxy.capture import extract_model


def resolve_billing_model(
    *,
    provider_slug: str | None,
    request_payload: Any | None,
    upstream_model: str | None,
    response_model: str | None,
    record_model: str | None,
) -> str | None:
    base_model = _first_model(
        upstream_model,
        response_model,
        record_model,
        extract_model(request_payload),
    )
    if not base_model:
        return None

    if provider_slug == "openrouter":
        endpoint_model = _openrouter_endpoint_model(request_payload, base_model)
        if endpoint_model:
            return endpoint_model

    if provider_slug == "huggingface-router":
        return _hf_router_model(upstream_model or base_model, response_model) or base_model

    return base_model


def _first_model(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _hf_router_model(upstream_model: str | None, response_model: str | None) -> str | None:
    if not upstream_model or ":" not in upstream_model:
        return None
    base_model, _, provider = upstream_model.rpartition(":")
    if not base_model or not provider:
        return None
    if not response_model or response_model == base_model:
        return upstream_model
    return None


def _openrouter_endpoint_model(request_payload: Any | None, base_model: str) -> str | None:
    if not isinstance(request_payload, dict):
        return None
    provider = request_payload.get("provider")
    if not isinstance(provider, dict):
        return None
    if _openrouter_fallbacks_enabled(provider):
        return None

    endpoint_tags = _single_provider_tag(provider.get("order")) or _single_provider_tag(
        provider.get("only")
    )
    if not endpoint_tags:
        return None
    return f"{base_model}@{endpoint_tags}"


def _single_provider_tag(value: object) -> str | None:
    if isinstance(value, str):
        tag = value.strip()
        return tag or None
    if not isinstance(value, list | tuple):
        return None
    tags: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[0] if len(tags) == 1 else None


def _openrouter_fallbacks_enabled(provider: dict[str, object]) -> bool:
    value = provider.get("allow_fallbacks", provider.get("allowFallbacks", True))
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return True
