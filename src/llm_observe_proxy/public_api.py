from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select

from llm_observe_proxy.admin import (
    _filter_routes,
    _paginated,
    _route_api_row,
    _route_sample_request,
    _sample_routing_decision,
)
from llm_observe_proxy.admin import (
    end_run_api as _admin_end_run_api,
)
from llm_observe_proxy.admin import (
    pause_run_api as _admin_pause_run_api,
)
from llm_observe_proxy.admin import (
    request_detail_api as _admin_request_detail_api,
)
from llm_observe_proxy.admin import (
    requests_api as _admin_requests_api,
)
from llm_observe_proxy.admin import (
    resume_run_api as _admin_resume_run_api,
)
from llm_observe_proxy.admin import (
    run_detail_api as _admin_run_detail_api,
)
from llm_observe_proxy.admin import (
    runs_api as _admin_runs_api,
)
from llm_observe_proxy.admin import (
    start_run_api as _admin_start_run_api,
)
from llm_observe_proxy.database import (
    DEFAULT_ROUTE_SEED_OWNER,
    ModelProvider,
    ModelRouteDB,
    RequestRecord,
    SessionFactory,
    list_model_routes_db,
    session_scope,
)
from llm_observe_proxy.routing import model_route_api_key_state, model_route_display

router = APIRouter(prefix="/api", tags=["public api"])


@router.get("/models", response_model=None, summary="List routeable models")
async def list_models_api(
    request: Request,
    search: str = "",
    provider: str = "",
    status: str = "active",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        rows = _model_route_rows(session, request.app.state.settings)
    filtered = _filter_routes(rows, search=search, status=status, provider=provider)
    return _paginated([_public_model_row(row) for row in filtered], page, per_page)


@router.get("/models/suggest", response_model=None, summary="Suggest model names")
async def suggest_models_api(
    request: Request,
    q: str = "",
    limit: int = Query(10, ge=1, le=50),
):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return {
            "items": _model_suggestion_rows(
                session,
                request.app.state.settings,
                q=q,
                limit=limit,
            )
        }


@router.get("/models/lookup", response_model=None, summary="Lookup model routing")
async def lookup_model_api(
    request: Request,
    model: str = Query(..., min_length=1),
    provider_slug: str = "",
):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        try:
            return _model_lookup_row(
                request,
                session,
                model.strip(),
                provider_slug=provider_slug.strip() or None,
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)


@router.get("/requests", response_model=None, summary="List captured requests")
async def requests_api(
    request: Request,
    endpoint: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    route: str | None = None,
    status: str | None = None,
    run: str | None = None,
    stream: str | None = None,
    image: str | None = None,
    tool: str | None = None,
    error: str | None = None,
    slow: str | None = None,
    large: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    return await _admin_requests_api(
        request,
        endpoint=endpoint,
        model=model,
        provider=provider,
        route=route,
        status=status,
        run=run,
        stream=stream,
        image=image,
        tool=tool,
        error=error,
        slow=slow,
        large=large,
        page=page,
        per_page=per_page,
    )


@router.get("/requests/{record_id}", response_model=None, summary="Get captured request detail")
async def request_detail_api(request: Request, record_id: int, mode: str = "auto"):
    return await _admin_request_detail_api(request, record_id, mode=mode)


@router.get("/runs", response_model=None, summary="List task runs")
async def runs_api(request: Request):
    return await _admin_runs_api(request)


@router.post("/runs/start", response_model=None, summary="Start a task run")
async def start_run_api(request: Request, payload: dict[str, object] | None = None):
    return await _admin_start_run_api(request, payload=payload)


@router.post("/runs/end", response_model=None, summary="End the active task run")
async def end_run_api(request: Request):
    return await _admin_end_run_api(request)


@router.post("/runs/pause", response_model=None, summary="Pause the active task run")
async def pause_run_api(request: Request):
    return await _admin_pause_run_api(request)


@router.post("/runs/{run_id}/resume", response_model=None, summary="Resume a task run")
async def resume_run_api(request: Request, run_id: int):
    return await _admin_resume_run_api(request, run_id)


@router.get("/runs/{run_id}", response_model=None, summary="Get task run detail")
async def run_detail_api(
    request: Request,
    run_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    return await _admin_run_detail_api(request, run_id, page=page, per_page=per_page)


@router.get("/runs/{run_id}/stats", response_model=None, summary="Get task run stats")
async def run_stats_api(request: Request, run_id: int):
    result = await _admin_run_detail_api(request, run_id, page=1, per_page=1)
    if isinstance(result, JSONResponse):
        return result
    return {
        "run": result["run"],
        "stats": result["stats"],
        "active_run": result["active_run"],
        "upstream_url": result["upstream_url"],
        "poll_interval_ms": result["poll_interval_ms"],
    }


@router.get(
    "/runs/{run_id}/requests",
    response_model=None,
    summary="List requests captured during a task run",
)
async def run_requests_api(
    request: Request,
    run_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    result = await _admin_run_detail_api(request, run_id, page=page, per_page=per_page)
    if isinstance(result, JSONResponse):
        return result
    return {
        "run": result["run"],
        "items": result["items"],
        "pagination": result["pagination"],
        "upstream_url": result["upstream_url"],
        "poll_interval_ms": result["poll_interval_ms"],
    }


def _model_route_rows(session, settings) -> list[dict[str, object]]:
    providers = {
        provider.slug: provider.name
        for provider in session.scalars(select(ModelProvider))
    }
    rows: list[dict[str, object]] = []
    for route in settings.model_routes:
        row = model_route_display(route)
        row["id"] = None
        row["incoming_model"] = row["model"]
        row["source"] = "startup"
        row["provider_name"] = providers.get(route.provider_slug or "")
        row["managed"] = False
        row["status"] = "active" if route.active else "inactive"
        rows.append(row)
    for route in list_model_routes_db(session, active_only=False):
        row = _route_api_row(session, route)
        row["model"] = row["incoming_model"]
        row["source"] = "seeded" if route.managed_by == DEFAULT_ROUTE_SEED_OWNER else "ui"
        row["managed"] = route.managed_by == DEFAULT_ROUTE_SEED_OWNER
        rows.append(row)
    return rows


def _public_model_row(row: dict[str, object]) -> dict[str, object]:
    client_model = str(row.get("incoming_model") or row.get("model") or "")
    return {
        "client_model": client_model,
        "status": row.get("status", "active"),
        "route": client_model,
        "match_type": row.get("match_type"),
        "provider_slug": row.get("provider_slug"),
        "provider_name": row.get("provider_name"),
        "api_key_state": row.get("api_key_state"),
        "upstream_url": row.get("upstream_url"),
        "upstream_model": row.get("upstream_model") or client_model,
        "source": row.get("source"),
        "managed": bool(row.get("managed")),
    }


def _model_lookup_row(
    request: Request,
    session,
    model: str,
    *,
    provider_slug: str | None = None,
) -> dict[str, object]:
    payload = {"model": model}
    decision = _sample_routing_decision(
        request,
        session,
        payload,
        provider_slug=provider_slug,
    )
    provider = (
        session.get(ModelProvider, decision.provider_slug)
        if decision.provider_slug
        else None
    )
    status = (
        "matched"
        if decision.model_route
        else "fallback"
        if decision.fallback_used
        else "unmatched"
    )
    sample = _route_sample_request(
        request,
        session,
        model,
        provider_slug=provider_slug,
    )
    return {
        "client_model": model,
        "status": status,
        "route": decision.model_route,
        "match_type": decision.match_type,
        "provider_slug": decision.provider_slug,
        "provider_name": provider.name if provider else decision.fallback_provider_name,
        "api_key_state": model_route_api_key_state(decision),
        "upstream_url": decision.upstream_base_url,
        "upstream_model": decision.upstream_model,
        "sample_request": sample,
    }


def _model_suggestion_rows(session, settings, *, q: str, limit: int) -> list[dict[str, object]]:
    query = q.strip()
    route_rows = _route_suggestion_rows(session, query=query, limit=limit)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in route_rows:
        seen.add(row["model"])
        rows.append(row)
    for row in _startup_route_suggestion_rows(settings, query=query, limit=limit):
        if row["model"] not in seen:
            seen.add(row["model"])
            rows.append(row)
    remaining = max(0, limit - len(rows))
    if remaining:
        for row in _recent_model_suggestion_rows(session, query=query, limit=remaining):
            if row["model"] not in seen:
                seen.add(row["model"])
                rows.append(row)
    return rows[:limit]


def _route_suggestion_rows(session, *, query: str, limit: int) -> list[dict[str, object]]:
    stmt = (
        select(ModelRouteDB, ModelProvider.name)
        .outerjoin(ModelProvider, ModelRouteDB.provider_slug == ModelProvider.slug)
        .where(ModelRouteDB.active.is_(True))
        .order_by(ModelRouteDB.priority, ModelRouteDB.incoming_model)
        .limit(limit)
    )
    if query:
        stmt = stmt.where(ModelRouteDB.incoming_model.like(f"{query}%"))
    rows = session.execute(stmt).all()
    return [
        {
            "model": route.incoming_model,
            "client_model": route.incoming_model,
            "source": "route",
            "provider_slug": route.provider_slug,
            "provider_name": provider_name,
            "upstream_model": route.effective_upstream_model,
            "request_count": None,
            "last_used_at": None,
        }
        for route, provider_name in rows
    ]


def _startup_route_suggestion_rows(settings, *, query: str, limit: int) -> list[dict[str, object]]:
    query_lower = query.lower()
    rows: list[dict[str, object]] = []
    for route in settings.model_routes:
        if not route.active:
            continue
        if query_lower and not route.model.lower().startswith(query_lower):
            continue
        rows.append(
            {
                "model": route.model,
                "client_model": route.model,
                "source": "route",
                "provider_slug": route.provider_slug,
                "provider_name": None,
                "upstream_model": route.effective_upstream_model,
                "request_count": None,
                "last_used_at": None,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _recent_model_suggestion_rows(session, *, query: str, limit: int) -> list[dict[str, object]]:
    stmt = (
        select(
            RequestRecord.model,
            func.count(RequestRecord.id),
            func.max(RequestRecord.created_at),
        )
        .where(RequestRecord.model.is_not(None))
        .group_by(RequestRecord.model)
        .order_by(desc(func.max(RequestRecord.created_at)))
        .limit(limit)
    )
    if query:
        stmt = stmt.where(RequestRecord.model.like(f"{query}%"))
    rows = session.execute(stmt).all()
    return [
        {
            "model": row[0],
            "client_model": row[0],
            "source": "recent",
            "provider_slug": None,
            "provider_name": None,
            "upstream_model": None,
            "request_count": int(row[1] or 0),
            "last_used_at": _isoformat(row[2]),
        }
        for row in rows
        if row[0]
    ]


def _isoformat(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")
