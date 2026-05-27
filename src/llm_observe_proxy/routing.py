from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from llm_observe_proxy.capture import extract_model
from llm_observe_proxy.config import ModelRoute, Settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from llm_observe_proxy.database import ModelRouteDB


@dataclass(frozen=True)
class ResolvedRoute:
    incoming_model: str
    match_type: str
    upstream_url: str
    upstream_model: str
    provider_slug: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    fixes: tuple[str, ...] = ()
    priority: int = 50
    active: bool = True
    source: str = "db"
    sort_index: int = 0
    db_id: int | None = None
    override_fallback: bool = False
    managed_by: str | None = None


@dataclass(frozen=True)
class RoutingDecision:
    requested_model: str | None
    route: ModelRoute | None = None
    route_db: ModelRouteDB | None = None
    resolved_route: ResolvedRoute | None = None
    match_type: str | None = None
    match_source: str = "none"
    fallback_used: bool = False
    fallback_provider_slug: str | None = None
    fallback_provider_name: str | None = None
    fallback_model: str | None = None
    fallback_upstream_url: str | None = None
    fallback_api_key_env: str | None = None
    fallback_fixes: tuple[str, ...] = ()

    @property
    def model_route(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.incoming_model
        if self.route:
            return self.route.model
        if self.route_db:
            return self.route_db.incoming_model
        return None

    @property
    def upstream_base_url(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.upstream_url
        if self.route:
            return self.route.upstream_url
        if self.route_db:
            return self.route_db.upstream_url
        return self.fallback_upstream_url

    @property
    def upstream_model(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.upstream_model
        if self.route:
            return self.route.effective_upstream_model
        if self.route_db:
            return self.route_db.effective_upstream_model
        return self.fallback_model

    @property
    def provider_slug(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.provider_slug
        if self.route:
            return self.route.provider_slug
        if self.route_db:
            return self.route_db.provider_slug
        return self.fallback_provider_slug

    @property
    def fixes(self) -> tuple[str, ...]:
        if self.resolved_route:
            return self.resolved_route.fixes
        if self.route:
            return self.route.fixes
        if self.route_db:
            return self.route_db.fixes
        return self.fallback_fixes

    @property
    def api_key_env(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.api_key_env
        if self.route:
            return self.route.api_key_env
        if self.route_db:
            return self.route_db.api_key_env
        return self.fallback_api_key_env

    @property
    def api_key(self) -> str | None:
        if self.resolved_route:
            return self.resolved_route.api_key
        if self.route:
            return self.route.api_key
        return None


@dataclass(frozen=True)
class RouteSimulationResult:
    status: str
    matched_route: str | None
    match_type: str | None
    upstream_url: str | None
    upstream_model: str | None
    provider_slug: str | None
    provider_name: str | None
    api_key_state: str | None
    compatibility_fixes: tuple[str, ...]


def select_model_route(
    request_payload: Any | None,
    settings: Settings,
    model_routes: Iterable[ModelRoute] | None = None,
    session: Session | None = None,
) -> RoutingDecision:
    requested_model = extract_model(request_payload)
    if not requested_model or not isinstance(request_payload, dict):
        return RoutingDecision(requested_model=requested_model)

    routes = (
        get_resolved_routes(session, settings)
        if session is not None
        else [_startup_route_to_resolved(route, index) for index, route in enumerate(
            model_routes if model_routes is not None else settings.model_routes,
        )]
    )
    matches = [route for route in routes if route.active and _match_route(route, requested_model)]
    if matches:
        selected = sorted(matches, key=_route_sort_key)[0]
        return RoutingDecision(
            requested_model=requested_model,
            route=selected_to_model_route(selected) if selected.source == "startup" else None,
            resolved_route=selected,
            match_type=selected.match_type,
            match_source=selected.source,
        )

    if session is None:
        return RoutingDecision(requested_model=requested_model)
    return _fallback_decision(session, requested_model)


def get_resolved_routes(session: Session, settings: Settings) -> list[ResolvedRoute]:
    from llm_observe_proxy.database import list_model_routes_db

    routes = [
        _startup_route_to_resolved(route, index)
        for index, route in enumerate(settings.model_routes)
    ]
    routes.extend(
        _db_route_to_resolved(route, index + len(routes))
        for index, route in enumerate(list_model_routes_db(session))
    )
    return sorted(routes, key=_route_sort_key)


def simulate_route_resolution(
    incoming_model: str,
    session: Session,
    settings: Settings,
) -> RouteSimulationResult:
    decision = select_model_route({"model": incoming_model}, settings, session=session)
    provider_name = decision.fallback_provider_name
    if decision.provider_slug:
        from llm_observe_proxy.database import ModelProvider

        provider = session.get(ModelProvider, decision.provider_slug)
        provider_name = provider.name if provider else provider_name
    status = (
        "matched"
        if decision.model_route
        else "fallback"
        if decision.fallback_used
        else "no_match"
    )
    api_key_state = _api_key_state_for_decision(decision)
    if api_key_state == "missing":
        status = "missing_api_key"
    return RouteSimulationResult(
        status=status,
        matched_route=decision.model_route,
        match_type=decision.match_type,
        upstream_url=decision.upstream_base_url,
        upstream_model=decision.upstream_model,
        provider_slug=decision.provider_slug,
        provider_name=provider_name,
        api_key_state=api_key_state,
        compatibility_fixes=decision.fixes,
    )


def build_forward_body(
    request_body: bytes,
    request_payload: Any | None,
    decision: RoutingDecision,
) -> bytes:
    if not isinstance(request_payload, dict) or not decision.upstream_model:
        return request_body
    requested_model = extract_model(request_payload)
    openrouter_model, openrouter_provider = _openrouter_forward_target(decision)
    if openrouter_model and openrouter_provider:
        forward_payload = dict(request_payload)
        forward_payload["model"] = openrouter_model
        provider_options = forward_payload.get("provider")
        if not isinstance(provider_options, dict):
            provider_options = {}
        else:
            provider_options = dict(provider_options)
        provider_options["order"] = [openrouter_provider]
        provider_options["allow_fallbacks"] = False
        forward_payload["provider"] = provider_options
        return json.dumps(
            forward_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    if requested_model == decision.upstream_model:
        return request_body

    forward_payload = dict(request_payload)
    forward_payload["model"] = decision.upstream_model
    return json.dumps(forward_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _openrouter_forward_target(decision: RoutingDecision) -> tuple[str | None, str | None]:
    if decision.provider_slug != "openrouter":
        return None, None
    for value in (decision.upstream_model, decision.model_route, decision.requested_model):
        if not value:
            continue
        base_model, separator, provider_tag = value.partition("@")
        if separator and base_model and provider_tag:
            return base_model, provider_tag
    upstream_model = decision.upstream_model
    model_route = decision.model_route
    if upstream_model and model_route and model_route.startswith(f"{upstream_model}:"):
        provider_tag = model_route[len(upstream_model) + 1 :]
        if provider_tag:
            return upstream_model, provider_tag
    return None, None


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

    if not decision.api_key and not decision.api_key_env:
        return forwarded
    _remove_header(forwarded, "authorization")
    api_key = resolve_model_route_api_key(decision)
    if not api_key:
        return forwarded
    forwarded["Authorization"] = f"Bearer {api_key}"
    return forwarded


def resolve_model_route_api_key(route: ModelRoute | ResolvedRoute | RoutingDecision) -> str | None:
    api_key = (
        route.api_key
        if isinstance(route, RoutingDecision)
        else getattr(route, "api_key", None)
    )
    api_key_env = (
        route.api_key_env
        if isinstance(route, RoutingDecision)
        else getattr(route, "api_key_env", None)
    )
    if api_key:
        return api_key
    if api_key_env:
        value = os.getenv(api_key_env)
        return value.strip() if value and value.strip() else None
    return None


def model_route_api_key_state(route: ModelRoute | ResolvedRoute | RoutingDecision) -> str:
    if getattr(route, "api_key", None):
        return "configured"
    api_key_env = getattr(route, "api_key_env", None)
    if api_key_env:
        return "configured" if resolve_model_route_api_key(route) else "missing"
    return "not configured"


def model_route_display(route: ModelRoute | ModelRouteDB) -> dict[str, object]:
    match_type = getattr(route, "match_type", "exact")
    model = getattr(route, "incoming_model", getattr(route, "model", ""))
    upstream_model = getattr(route, "effective_upstream_model", None)
    if upstream_model is None:
        upstream_model = getattr(route, "upstream_model", None) or model
    return {
        "id": getattr(route, "id", None),
        "model": model,
        "incoming_model": model,
        "match_type": match_type,
        "upstream_url": route.upstream_url,
        "upstream_model": upstream_model,
        "provider_slug": route.provider_slug,
        "fixes": route.fixes,
        "api_key_env": route.api_key_env,
        "api_key_state": model_route_api_key_state(route),
        "priority": getattr(route, "priority", 50),
        "active": getattr(route, "active", True),
        "override_fallback": getattr(route, "override_fallback", False),
        "managed_by": getattr(route, "managed_by", None),
    }


def selected_to_model_route(route: ResolvedRoute) -> ModelRoute:
    return ModelRoute(
        model=route.incoming_model,
        upstream_url=route.upstream_url,
        upstream_model=route.upstream_model,
        provider_slug=route.provider_slug,
        api_key=route.api_key,
        api_key_env=route.api_key_env,
        fixes=route.fixes,
    )


def _startup_route_to_resolved(route: ModelRoute, index: int) -> ResolvedRoute:
    return ResolvedRoute(
        incoming_model=route.model,
        match_type="exact",
        upstream_url=route.upstream_url,
        upstream_model=route.effective_upstream_model,
        provider_slug=route.provider_slug,
        api_key_env=route.api_key_env,
        api_key=route.api_key,
        fixes=route.fixes,
        priority=0,
        active=True,
        source="startup",
        sort_index=index,
    )


def _db_route_to_resolved(route: ModelRouteDB, index: int) -> ResolvedRoute:
    return ResolvedRoute(
        incoming_model=route.incoming_model,
        match_type=route.match_type,
        upstream_url=route.upstream_url,
        upstream_model=route.effective_upstream_model,
        provider_slug=route.provider_slug,
        api_key_env=route.api_key_env,
        fixes=route.fixes,
        priority=route.priority,
        active=route.active,
        source="db",
        sort_index=index,
        db_id=route.id,
        override_fallback=route.override_fallback,
        managed_by=route.managed_by,
    )


def _matches_exact(pattern: str, model: str) -> bool:
    return pattern == model


def _matches_prefix(pattern: str, model: str) -> bool:
    if not pattern.endswith("*"):
        return False
    return model.startswith(pattern[:-1])


def _match_route(route: ResolvedRoute, model: str) -> bool:
    if route.match_type == "prefix":
        return _matches_prefix(route.incoming_model, model)
    return _matches_exact(route.incoming_model, model)


def _route_sort_key(route: ResolvedRoute) -> tuple[int, int, int, int]:
    match_rank = 0 if route.match_type == "exact" else 1
    return (route.priority, match_rank, -len(route.incoming_model.rstrip("*")), route.sort_index)


def _fallback_decision(session: Session, requested_model: str) -> RoutingDecision:
    from llm_observe_proxy.database import (
        ModelProvider,
        get_default_compat_fixes,
        get_default_model,
        get_default_provider_slug,
        is_fallback_enabled,
    )

    if not is_fallback_enabled(session):
        return RoutingDecision(requested_model=requested_model)
    provider_slug = get_default_provider_slug(session)
    default_model = get_default_model(session)
    provider = session.get(ModelProvider, provider_slug) if provider_slug else None
    if provider is None or not provider.upstream_url or not default_model:
        return RoutingDecision(requested_model=requested_model)
    settings = Settings()
    return RoutingDecision(
        requested_model=requested_model,
        match_source="fallback",
        fallback_used=True,
        fallback_provider_slug=provider.slug,
        fallback_provider_name=provider.name,
        fallback_model=default_model,
        fallback_upstream_url=provider.upstream_url,
        fallback_api_key_env=provider.api_key_env,
        fallback_fixes=get_default_compat_fixes(session, settings),
    )


def _api_key_state_for_decision(decision: RoutingDecision) -> str:
    if not decision.api_key_env and not decision.api_key:
        return "not_configured"
    return "configured" if resolve_model_route_api_key(decision) else "missing"


def _remove_header(headers: dict[str, str], name: str) -> None:
    lowered = name.lower()
    for key in list(headers):
        if key.lower() == lowered:
            del headers[key]
