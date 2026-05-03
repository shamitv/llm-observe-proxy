from __future__ import annotations

import json

import pytest

from llm_observe_proxy.config import ModelRoute, Settings, get_settings, load_model_routes
from llm_observe_proxy.routing import (
    RoutingDecision,
    build_forward_body,
    build_forward_headers,
    model_route_api_key_state,
    resolve_model_route_api_key,
    select_model_route,
)


def test_model_routes_parse_from_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_OBSERVE_MODELS_FILE", raising=False)
    monkeypatch.setenv(
        "LLM_OBSERVE_MODELS_JSON",
        json.dumps(
            [
                {
                    "model": " local-qwen ",
                    "upstream_url": "http://localhost:8000/v1/",
                    "upstream_model": " qwen3-coder-30b ",
                }
            ]
        ),
    )

    settings = get_settings()

    assert len(settings.model_routes) == 1
    route = settings.model_routes[0]
    assert route.model == "local-qwen"
    assert route.upstream_url == "http://localhost:8000/v1"
    assert route.effective_upstream_model == "qwen3-coder-30b"


def test_model_routes_file_wins_over_json_env(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes_file = tmp_path / "models.json"
    routes_file.write_text(
        json.dumps([{"model": "file-model", "upstream_url": "http://localhost:8001/v1"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "LLM_OBSERVE_MODELS_JSON",
        json.dumps([{"model": "env-model", "upstream_url": "http://localhost:8002/v1"}]),
    )

    routes = load_model_routes(
        models_file=str(routes_file),
        models_json='[{"model":"env-model","upstream_url":"http://localhost:8002/v1"}]',
    )

    assert [route.model for route in routes] == ["file-model"]
    assert routes[0].effective_upstream_model == "file-model"


def test_model_routes_reject_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="Duplicate model route"):
        load_model_routes(
            models_json=json.dumps(
                [
                    {"model": "gpt-test", "upstream_url": "http://localhost:8000/v1"},
                    {"model": "gpt-test", "upstream_url": "http://localhost:8001/v1"},
                ]
            )
        )

    with pytest.raises(ValueError, match="must point to a /v1"):
        load_model_routes(
            models_json=json.dumps([{"model": "gpt-test", "upstream_url": "http://localhost"}])
        )

    with pytest.raises(ValueError, match="both api_key and api_key_env"):
        load_model_routes(
            models_json=json.dumps(
                [
                    {
                        "model": "gpt-test",
                        "upstream_url": "http://localhost:8000/v1",
                        "api_key": "direct",
                        "api_key_env": "UPSTREAM_KEY",
                    }
                ]
            )
        )


def test_routing_selects_exact_model_and_rewrites_body() -> None:
    route = ModelRoute(
        model="local-qwen",
        upstream_url="http://localhost:8000/v1",
        upstream_model="qwen3-coder-30b",
    )
    settings = Settings(model_routes=(route,))
    payload = {"model": "local-qwen", "messages": [{"role": "user", "content": "hello"}]}
    body = json.dumps(payload).encode()

    decision = select_model_route(payload, settings)
    forward_body = build_forward_body(body, payload, decision)

    assert decision.model_route == "local-qwen"
    assert decision.upstream_base_url == "http://localhost:8000/v1"
    assert decision.upstream_model == "qwen3-coder-30b"
    assert json.loads(forward_body)["model"] == "qwen3-coder-30b"
    assert payload["model"] == "local-qwen"


def test_routing_falls_back_for_unknown_missing_and_non_json_models() -> None:
    settings = Settings(
        model_routes=(ModelRoute(model="configured", upstream_url="http://localhost:8000/v1"),)
    )

    assert select_model_route({"model": "unknown"}, settings).route is None
    assert select_model_route({"messages": []}, settings).route is None
    assert select_model_route(None, settings).route is None
    assert select_model_route(["configured"], settings).route is None


def test_route_api_key_resolution_and_header_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTREAM_KEY", " upstream-secret ")
    injected = ModelRoute(
        model="openai-mini",
        upstream_url="https://api.openai.com/v1",
        api_key_env="UPSTREAM_KEY",
    )
    decision = RoutingDecision(requested_model="openai-mini", route=injected)

    headers = build_forward_headers(
        {"Authorization": "Bearer client", "X-Client-Request-Id": "trace-1", "Host": "proxy"},
        decision,
        {"host"},
    )

    assert resolve_model_route_api_key(injected) == "upstream-secret"
    assert model_route_api_key_state(injected) == "configured"
    assert headers["Authorization"] == "Bearer upstream-secret"
    assert headers["X-Client-Request-Id"] == "trace-1"
    assert "Host" not in headers


def test_missing_route_api_key_env_drops_client_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_UPSTREAM_KEY", raising=False)
    route = ModelRoute(
        model="openai-mini",
        upstream_url="https://api.openai.com/v1",
        api_key_env="MISSING_UPSTREAM_KEY",
    )

    headers = build_forward_headers(
        {"authorization": "Bearer client", "x-client-request-id": "trace-1"},
        RoutingDecision(requested_model="openai-mini", route=route),
        set(),
    )

    assert model_route_api_key_state(route) == "missing"
    assert "authorization" not in {key.lower() for key in headers}
    assert headers["x-client-request-id"] == "trace-1"


def test_route_without_key_preserves_client_authorization() -> None:
    route = ModelRoute(model="local-qwen", upstream_url="http://localhost:8000/v1")

    headers = build_forward_headers(
        {"authorization": "Bearer client"},
        RoutingDecision(requested_model="local-qwen", route=route),
        set(),
    )

    assert model_route_api_key_state(route) == "not configured"
    assert headers["authorization"] == "Bearer client"
