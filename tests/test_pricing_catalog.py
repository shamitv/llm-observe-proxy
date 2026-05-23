from __future__ import annotations

from decimal import Decimal

from llm_observe_proxy.billing import resolve_billing_model
from llm_observe_proxy.pricing_catalog import (
    normalize_hf_catalog,
    normalize_openrouter_catalog,
)


def test_normalizes_hf_router_provider_prices() -> None:
    rows = normalize_hf_catalog(
        {
            "data": [
                {
                    "id": "Qwen/Qwen3.6-35B-A3B",
                    "providers": [
                        {
                            "provider": "deepinfra",
                            "status": "live",
                            "context_length": 65536,
                            "pricing": {"input": 0.15, "output": 0.95},
                            "supports_tools": True,
                        },
                        {"provider": "missing-prices", "status": "live"},
                    ],
                }
            ]
        },
        checked_at="2026-05-23",
    )

    models = {row.model: row for row in rows}
    assert models["Qwen/Qwen3.6-35B-A3B"].input_usd_per_million == Decimal("0.15")
    assert models["Qwen/Qwen3.6-35B-A3B:deepinfra"].output_usd_per_million == Decimal(
        "0.95"
    )
    assert models["Qwen/Qwen3.6-35B-A3B:deepinfra"].supports_tools is True
    assert "missing-prices" not in "\n".join(models)


def test_normalizes_openrouter_base_and_endpoint_prices() -> None:
    rows = normalize_openrouter_catalog(
        {
            "data": [
                {
                    "id": "qwen/qwen3-coder",
                    "name": "Qwen: Qwen3 Coder",
                    "canonical_slug": "qwen/qwen3-coder",
                    "context_length": 262144,
                    "pricing": {
                        "prompt": "0.00000022",
                        "completion": "0.0000018",
                        "input_cache_read": "0.00000002",
                        "input_cache_write": "0.00000003",
                    },
                    "links": {"details": "/api/v1/models/qwen/qwen3-coder/endpoints"},
                    "supported_parameters": ["tools"],
                }
            ]
        },
        endpoint_payloads={
            "qwen/qwen3-coder": {
                "data": {
                    "endpoints": [
                        {
                            "provider_name": "Google",
                            "tag": "google-vertex/us-south1",
                            "context_length": 262144,
                            "pricing": {
                                "prompt": "0.00000030",
                                "completion": "0.00000200",
                            },
                            "supported_parameters": ["tools", "temperature"],
                        },
                        {"provider_name": "No Price", "tag": "no-price"},
                    ]
                }
            }
        },
        checked_at="2026-05-23",
    )

    models = {row.model: row for row in rows}
    assert models["qwen/qwen3-coder"].input_usd_per_million == Decimal("0.22000000")
    assert models["qwen/qwen3-coder"].cached_input_usd_per_million == Decimal("0.02000000")
    endpoint = models["qwen/qwen3-coder@google-vertex/us-south1"]
    assert endpoint.input_usd_per_million == Decimal("0.30000000")
    assert endpoint.output_usd_per_million == Decimal("2.00000000")
    assert endpoint.external_provider == "Google"
    assert "qwen/qwen3-coder:no-price" not in models


def test_router_specific_billing_model_resolution() -> None:
    hf_model = resolve_billing_model(
        provider_slug="huggingface-router",
        request_payload={"model": "Qwen/Qwen3.6-35B-A3B:deepinfra"},
        upstream_model="Qwen/Qwen3.6-35B-A3B:deepinfra",
        response_model="Qwen/Qwen3.6-35B-A3B",
        record_model=None,
    )
    openrouter_model = resolve_billing_model(
        provider_slug="openrouter",
        request_payload={
            "model": "qwen/qwen3-coder",
            "provider": {
                "order": ["google-vertex/us-south1"],
                "allow_fallbacks": False,
            },
        },
        upstream_model="qwen/qwen3-coder",
        response_model="qwen/qwen3-coder",
        record_model=None,
    )
    ambiguous_openrouter_model = resolve_billing_model(
        provider_slug="openrouter",
        request_payload={
            "model": "qwen/qwen3-coder",
            "provider": {"order": ["google-vertex/us-south1", "deepinfra"]},
        },
        upstream_model="qwen/qwen3-coder",
        response_model="qwen/qwen3-coder",
        record_model=None,
    )

    assert hf_model == "Qwen/Qwen3.6-35B-A3B:deepinfra"
    assert openrouter_model == "qwen/qwen3-coder@google-vertex/us-south1"
    assert ambiguous_openrouter_model == "qwen/qwen3-coder"
