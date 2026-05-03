from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from llm_observe_proxy.capture import extract_model
from llm_observe_proxy.config import ModelRoute, Settings


@dataclass(frozen=True)
class RoutingDecision:
    requested_model: str | None
    route: ModelRoute | None = None

    @property
    def model_route(self) -> str | None:
        return self.route.model if self.route else None

    @property
    def upstream_base_url(self) -> str | None:
        return self.route.upstream_url if self.route else None

    @property
    def upstream_model(self) -> str | None:
        return self.route.effective_upstream_model if self.route else None


def select_model_route(
    request_payload: Any | None,
    settings: Settings,
    model_routes: Iterable[ModelRoute] | None = None,
) -> RoutingDecision:
    requested_model = extract_model(request_payload)
    if not requested_model or not isinstance(request_payload, dict):
        return RoutingDecision(requested_model=requested_model)

    routes = model_routes if model_routes is not None else settings.model_routes
    for route in routes:
        if route.model == requested_model:
            return RoutingDecision(requested_model=requested_model, route=route)
    return RoutingDecision(requested_model=requested_model)


def build_forward_body(
    request_body: bytes,
    request_payload: Any | None,
    decision: RoutingDecision,
) -> bytes:
    if decision.route is None or not isinstance(request_payload, dict):
        return request_body

    forward_payload = dict(request_payload)
    forward_payload["model"] = decision.route.effective_upstream_model
    return json.dumps(forward_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_forward_headers(
    headers: Any,
    decision: RoutingDecision,
    drop_headers: set[str],
) -> dict[str, str]:
    forwarded = {
        key: value
        for key, value in headers.items()
        if key.lower() not in {header.lower() for header in drop_headers}
    }

    route = decision.route
    if route is None or not (route.api_key or route.api_key_env):
        return forwarded

    _remove_header(forwarded, "authorization")
    api_key = resolve_model_route_api_key(route)
    if api_key:
        forwarded["Authorization"] = f"Bearer {api_key}"
    return forwarded


def resolve_model_route_api_key(route: ModelRoute) -> str | None:
    if route.api_key:
        return route.api_key
    if route.api_key_env:
        value = os.getenv(route.api_key_env)
        return value.strip() if value and value.strip() else None
    return None


def model_route_api_key_state(route: ModelRoute) -> str:
    if route.api_key:
        return "configured"
    if route.api_key_env:
        return "configured" if resolve_model_route_api_key(route) else "missing"
    return "not configured"


def model_route_display(route: ModelRoute) -> dict[str, str | None]:
    return {
        "model": route.model,
        "upstream_url": route.upstream_url,
        "upstream_model": route.effective_upstream_model,
        "api_key_env": route.api_key_env,
        "api_key_state": model_route_api_key_state(route),
    }


def _remove_header(headers: dict[str, str], name: str) -> None:
    lowered = name.lower()
    for key in list(headers):
        if key.lower() == lowered:
            del headers[key]
