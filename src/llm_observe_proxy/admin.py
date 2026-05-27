from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote, urlencode

import httpx
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Undefined, pass_context
from sqlalchemy import case, desc, func, or_, select
from starlette.templating import Jinja2Templates

from llm_observe_proxy.capture import (
    ExtractedTokenUsage,
    decode_json_bytes,
    extract_stream_token_usage,
    extract_token_usage,
)
from llm_observe_proxy.compatibility import (
    compatibility_fix_rows,
    fix_ids_text,
    normalize_fix_ids,
)
from llm_observe_proxy.config import normalize_upstream_url
from llm_observe_proxy.costing import (
    RunCostEstimate,
    backfill_missing_cost_estimates,
    estimate_run_cost,
)
from llm_observe_proxy.database import (
    DEFAULT_ROUTE_SEED_OWNER,
    ModelPrice,
    ModelProvider,
    ModelRouteDB,
    RequestRecord,
    SessionFactory,
    TaskRun,
    apply_default_model_routes,
    build_default_model_route_candidates,
    delete_model_price,
    delete_model_price_tier,
    delete_model_provider,
    delete_model_route_db,
    delete_ui_model_route,
    end_active_task_run,
    get_active_task_run,
    get_default_compat_fixes,
    get_effective_model_routes,
    get_expose_all_ips,
    get_fallback_summary,
    get_incoming_host,
    get_incoming_port,
    get_model_route_db,
    get_provider_usage_summary,
    get_route_usage_summary,
    get_task_run_stats,
    get_upstream_url,
    list_model_prices,
    list_model_providers,
    list_model_routes_db,
    list_task_runs_with_stats,
    pause_active_task_run,
    preview_default_model_routes,
    resume_task_run,
    session_scope,
    set_default_compat_fixes,
    set_default_model,
    set_default_provider_slug,
    set_fallback_enabled,
    set_incoming_server,
    set_setting,
    start_task_run,
    upsert_model_price,
    upsert_model_price_tier,
    upsert_model_provider,
    upsert_model_route_db,
)
from llm_observe_proxy.pricing_catalog import (
    CatalogFetchError,
    PricingCatalogRow,
    fetch_catalog_rows,
)
from llm_observe_proxy.rendering import escape_preview, render_payload
from llm_observe_proxy.routing import (
    ResolvedRoute,
    RoutingDecision,
    build_forward_body,
    build_forward_headers,
    model_route_display,
    select_model_route,
    simulate_route_resolution,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.filters["preview"] = escape_preview


@pass_context
def is_active_mode(context, mode: str) -> str:
    return "active" if context.get("mode") == mode else ""


templates.env.filters["active_mode"] = is_active_mode


def format_compact_number(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return "-"

    absolute = abs(number)
    if absolute < 1000:
        return _format_decimal(number, max_decimals=0)

    for divisor, suffix in (
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "k"),
    ):
        if absolute >= divisor:
            scaled = number / divisor
            return f"{_format_decimal(scaled, max_decimals=_compact_decimals(scaled))}{suffix}"

    return _format_decimal(number, max_decimals=0)


def format_compact_rate(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return "-"
    if abs(number) < 1000:
        return f"{number:.2f}"
    return format_compact_number(number)


def format_percent(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return "-"
    return f"{_format_decimal(number * 100, max_decimals=1)}%"


def format_duration_ms(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return "-"

    total_ms = max(0, int(round(number)))
    if total_ms < 1000:
        return f"{total_ms} ms"

    if total_ms < 60_000:
        seconds = total_ms / 1000
        return f"{_format_decimal(seconds, max_decimals=2)} s"

    total_seconds = int(round(total_ms / 1000))
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"

    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"

    days, hours = divmod(hours, 24)
    day_label = "day" if days == 1 else "days"
    return f"{days} {day_label} {hours}h" if hours else f"{days} {day_label}"


def format_utc_iso(value: object) -> str:
    timestamp = _coerce_datetime_utc(value)
    if timestamp is None:
        return ""
    return timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")


def format_utc_fallback(value: object, variant: str = "full") -> str:
    timestamp = _coerce_datetime_utc(value)
    if timestamp is None:
        return "-"
    if variant == "table":
        return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_usd(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return "-"
    absolute = abs(number)
    if absolute >= 1000:
        return f"${format_compact_number(number)}"
    if absolute == 0:
        return "$0.00"
    if absolute < 0.01:
        return f"${number:.6f}"
    if absolute < 1:
        return f"${number:.4f}"
    return f"${number:.2f}"


def _coerce_number(value: object) -> float | None:
    if value is None or isinstance(value, Undefined) or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        number = float(value)
    elif isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped == "-":
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if not math.isfinite(number):
        return None
    return number


def _coerce_datetime_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_decimal(value: float, *, max_decimals: int) -> str:
    text = f"{value:.{max_decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _compact_decimals(value: float) -> int:
    absolute = abs(value)
    if absolute < 10:
        return 2
    if absolute < 100:
        return 1
    return 0


templates.env.filters["compact_number"] = format_compact_number
templates.env.filters["compact_rate"] = format_compact_rate
templates.env.filters["duration_ms"] = format_duration_ms
templates.env.filters["utc_fallback"] = format_utc_fallback
templates.env.filters["utc_iso"] = format_utc_iso
templates.env.filters["usd"] = format_usd

router = APIRouter(prefix="/admin", include_in_schema=False)
SETTINGS_FALLBACK_RETURN_PATHS = frozenset(
    {"/admin/settings/server", "/admin/settings/routing", "/admin/settings/providers"}
)

TEST_PROMPT_DEFAULT = "Reply with a short upstream connectivity check."
TEST_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
DEFAULT_RUN_WHAT_IF_KEYS = ("openai:gpt-5.5", "openai:gpt-5.4-mini")
LIST_RESPONSE_PREVIEW_BYTES = 64 * 1024
SLOW_REQUEST_THRESHOLD_MS = 10_000
LARGE_REQUEST_TOKEN_THRESHOLD = 10_000


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
) -> HTMLResponse:
    upstream_url = _upstream_url_for_shell(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "upstream_url": upstream_url,
            "active_nav": "requests",
            "page_title": "Request Browser",
        },
    )


@router.get("/api/requests", response_model=None)
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
) -> dict[str, object]:
    session_factory: SessionFactory = request.app.state.session_factory
    status_filter = _optional_query_int(status, "status")
    run_filter = _optional_query_int(run, "run")
    with session_scope(session_factory) as session:
        stmt = select(RequestRecord)
        if endpoint:
            stmt = stmt.where(RequestRecord.endpoint.like(f"%{endpoint}%"))
        if model:
            stmt = stmt.where(RequestRecord.model == model)
        if provider:
            stmt = stmt.where(
                or_(
                    RequestRecord.billing_provider_slug == provider,
                    RequestRecord.billing_provider_name == provider,
                )
            )
        if route:
            stmt = stmt.where(RequestRecord.model_route == route)
        if status_filter is not None:
            stmt = stmt.where(RequestRecord.response_status == status_filter)
        if run_filter is not None:
            stmt = stmt.where(RequestRecord.task_run_id == run_filter)
        if stream == "1":
            stmt = stmt.where(RequestRecord.is_stream.is_(True))
        if image == "1":
            stmt = stmt.where(RequestRecord.has_images.is_(True))
        if tool == "1":
            stmt = stmt.where(RequestRecord.has_tool_calls.is_(True))
        if error == "1":
            stmt = stmt.where(_request_error_condition())
        if slow == "1":
            stmt = stmt.where(RequestRecord.duration_ms >= SLOW_REQUEST_THRESHOLD_MS)
        if large == "1":
            stmt = stmt.where(
                func.coalesce(
                    RequestRecord.billing_total_tokens,
                    RequestRecord.estimated_input_tokens,
                    0,
                )
                >= LARGE_REQUEST_TOKEN_THRESHOLD
            )

        total_records = _count_records(session, stmt)
        pagination = _pagination_context(
            request,
            total=total_records,
            page=page,
            per_page=per_page,
        )
        records = _request_list_items_for_page(session, stmt, pagination)
        models = [
            row[0]
            for row in session.execute(
                select(RequestRecord.model).where(RequestRecord.model.is_not(None)).distinct()
            )
        ]
        endpoints = [row[0] for row in session.execute(select(RequestRecord.endpoint).distinct())]
        providers = _request_provider_options(session)
        routes = [
            row[0]
            for row in session.execute(
                select(RequestRecord.model_route)
                .where(RequestRecord.model_route.is_not(None))
                .distinct()
                .order_by(RequestRecord.model_route)
            )
        ]
        run_options = session.scalars(select(TaskRun).order_by(desc(TaskRun.started_at))).all()
        stats = {
            "total": session.scalar(select(func.count()).select_from(RequestRecord)) or 0,
            "streams": session.scalar(
                select(func.count()).where(RequestRecord.is_stream.is_(True))
            )
            or 0,
            "images": session.scalar(
                select(func.count()).where(RequestRecord.has_images.is_(True))
            )
            or 0,
            "tools": session.scalar(
                select(func.count()).where(RequestRecord.has_tool_calls.is_(True))
            )
            or 0,
            "errors": session.scalar(select(func.count()).where(_request_error_condition()))
            or 0,
            "slow": session.scalar(
                select(func.count()).where(RequestRecord.duration_ms >= SLOW_REQUEST_THRESHOLD_MS)
            )
            or 0,
            "large": session.scalar(
                select(func.count()).where(
                    func.coalesce(
                        RequestRecord.billing_total_tokens,
                        RequestRecord.estimated_input_tokens,
                        0,
                    )
                    >= LARGE_REQUEST_TOKEN_THRESHOLD
                )
            )
            or 0,
        }
        upstream_url = get_upstream_url(session, request.app.state.settings)
        active_run = _task_run_summary(get_active_task_run(session), session)

    return {
        "items": [_record_list_item_json(record) for record in records],
        "models": models,
        "endpoints": endpoints,
        "filters": {
            "endpoint": endpoint or "",
            "model": model or "",
            "provider": provider or "",
            "route": route or "",
            "status": status_filter if status_filter is not None else "",
            "run": run_filter if run_filter is not None else "",
            "stream": stream == "1",
            "image": image == "1",
            "tool": tool == "1",
            "error": error == "1",
            "slow": slow == "1",
            "large": large == "1",
            "page": pagination["page"],
            "per_page": pagination["per_page"],
        },
        "provider_options": providers,
        "route_options": routes,
        "run_options": [
            _task_run_summary_json(_task_run_summary(task_run, session=None))
            for task_run in run_options
        ],
        "active_run": _task_run_summary_json(active_run),
        "stats": _stats_json(stats),
        "pagination": _pagination_json(pagination),
        "upstream_url": upstream_url,
        "poll_interval_ms": 1000,
    }


@router.get("/requests/{record_id}", response_class=HTMLResponse)
async def detail(request: Request, record_id: int, mode: str = "auto") -> HTMLResponse:
    upstream_url = _upstream_url_for_shell(request)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "record_id": record_id,
            "mode": _normalize_render_mode(mode),
            "upstream_url": upstream_url,
            "active_nav": "requests",
            "page_title": f"Request #{record_id}",
        },
    )


@router.get("/api/requests/{record_id}", response_model=None)
async def request_detail_api(
    request: Request,
    record_id: int,
    mode: str = "auto",
) -> dict[str, object] | JSONResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        record = session.get(RequestRecord, record_id)
        if record is None:
            return JSONResponse({"detail": "Request not found."}, status_code=404)
        images = [
            {
                "kind": image.kind,
                "mime_type": image.mime_type,
                "source": image.source,
                "data_base64": image.data_base64,
            }
            for image in record.images
        ]
        detail_record = _record_detail(record, now=datetime.now(UTC))
        upstream_url = get_upstream_url(session, request.app.state.settings)
        active_run = _task_run_summary(get_active_task_run(session), session)

    render_mode = _normalize_render_mode(mode)
    request_render = render_payload(
        detail_record["request_body"],
        detail_record["request_content_type"],
        "json",
    )
    response_render = render_payload(
        detail_record["response_body"],
        detail_record["response_content_type"],
        render_mode,
    )
    raw_response_render = (
        render_payload(
            detail_record["upstream_response_body_raw"],
            detail_record["response_content_type"],
            render_mode,
        )
        if detail_record["upstream_response_body_raw"]
        else None
    )
    return {
        "record": _record_detail_json(detail_record),
        "images": images,
        "request_render": _rendered_payload_json(request_render),
        "response_render": _rendered_payload_json(response_render),
        "raw_response_render": _rendered_payload_json(raw_response_render),
        "mode": response_render.mode if render_mode == "auto" else render_mode,
        "active_run": _task_run_summary_json(active_run),
        "upstream_url": upstream_url,
        "poll_interval_ms": 1000,
    }


@router.get("/runs", response_class=HTMLResponse)
async def runs(request: Request) -> HTMLResponse:
    upstream_url = _upstream_url_for_shell(request)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "upstream_url": upstream_url,
            "active_nav": "runs",
            "page_title": "Runs",
        },
    )


@router.get("/api/runs", response_model=None)
async def runs_api(request: Request) -> dict[str, object]:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        runs_with_stats = [
            _task_run_list_item(item["run"], item["stats"], session)
            for item in list_task_runs_with_stats(session)
        ]
        active_run = _task_run_summary(get_active_task_run(session), session)
        upstream_url = get_upstream_url(session, request.app.state.settings)
    total_requests = sum(int(run["request_count"] or 0) for run in runs_with_stats)
    total_tokens = sum(int(run["total_tokens"] or 0) for run in runs_with_stats)
    total_cost = sum(
        (run["total_cost_usd"] for run in runs_with_stats if run["total_cost_usd"] is not None),
        Decimal("0"),
    )

    return {
        "items": [_task_run_list_item_json(run) for run in runs_with_stats],
        "active_run": _task_run_summary_json(active_run),
        "stats": {
            "shown": len(runs_with_stats),
            "shown_display": format_compact_number(len(runs_with_stats)),
            "active": 1 if active_run else 0,
            "paused": sum(1 for run in runs_with_stats if run["is_paused"]),
            "total_requests": total_requests,
            "total_requests_display": format_compact_number(total_requests),
            "total_tokens": total_tokens,
            "total_tokens_display": format_compact_number(total_tokens),
            "total_cost_usd": _json_safe_number(total_cost),
            "total_cost_display": format_usd(total_cost),
        },
        "upstream_url": upstream_url,
        "poll_interval_ms": 1000,
    }


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request,
    run_id: int,
) -> HTMLResponse:
    upstream_url = _upstream_url_for_shell(request)
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run_id": run_id,
            "what_if_api_url": f"/admin/api/runs/{run_id}/what-if",
            "upstream_url": upstream_url,
            "active_nav": "runs",
            "page_title": f"Run #{run_id}",
        },
    )


@router.get("/api/runs/{run_id}", response_model=None)
async def run_detail_api(
    request: Request,
    run_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, object] | JSONResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = session.get(TaskRun, run_id)
        if task_run is None:
            return JSONResponse({"detail": "Run not found."}, status_code=404)
        request_stmt = select(RequestRecord).where(RequestRecord.task_run_id == run_id)
        total_records = _count_records(session, request_stmt)
        pagination = _pagination_context(
            request,
            total=total_records,
            page=page,
            per_page=per_page,
        )
        records = _request_list_items_for_page(session, request_stmt, pagination)
        stats = _task_run_stats_detail(task_run, session)
        active_run = _task_run_summary(get_active_task_run(session), session)
        upstream_url = get_upstream_url(session, request.app.state.settings)

    return {
        "run": _task_run_summary_json(_task_run_summary(task_run, session=None)),
        "items": [_record_list_item_json(record) for record in records],
        "stats": _task_run_stats_detail_json(stats),
        "what_if_api_url": f"/admin/api/runs/{run_id}/what-if",
        "pagination": _pagination_json(pagination),
        "active_run": _task_run_summary_json(active_run),
        "upstream_url": upstream_url,
        "poll_interval_ms": 1000,
    }


@router.get("/api/runs/{run_id}/what-if", response_model=None)
async def run_what_if_api(
    request: Request,
    run_id: int,
    key: Annotated[list[str] | None, Query()] = None,
) -> dict[str, object] | JSONResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = session.get(TaskRun, run_id)
        if task_run is None:
            return JSONResponse({"detail": "Run not found."}, status_code=404)
        return _run_what_if_context(
            _run_billing_usages(session, run_id),
            session,
            requested_keys=key,
            baseline=_run_current_cost_baseline(session, run_id),
        )


@router.post("/api/runs/start", response_model=None)
async def start_run_api(
    request: Request,
    payload: dict[str, object] | None = None,
) -> dict[str, object] | JSONResponse:
    payload = payload or {}
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            task_run = start_task_run(
                session,
                str(payload.get("name") or ""),
                str(payload.get("notes") or ""),
            )
            return {"run": _task_run_summary_json(_task_run_summary(task_run, session))}
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/api/runs/end", response_model=None)
async def end_run_api(request: Request) -> dict[str, object]:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = end_active_task_run(session)
        return {
            "run": _task_run_summary_json(_task_run_summary(task_run, session))
            if task_run
            else None
        }


@router.post("/api/runs/pause", response_model=None)
async def pause_run_api(request: Request) -> dict[str, object]:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = pause_active_task_run(session)
        return {
            "run": _task_run_summary_json(_task_run_summary(task_run, session))
            if task_run
            else None
        }


@router.post("/api/runs/{run_id}/resume", response_model=None)
async def resume_run_api(
    request: Request,
    run_id: int,
) -> dict[str, object] | JSONResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            task_run = resume_task_run(session, run_id)
            return {"run": _task_run_summary_json(_task_run_summary(task_run, session))}
    except LookupError:
        return JSONResponse({"detail": "Run not found."}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/runs/start", response_class=HTMLResponse)
async def start_run(
    request: Request,
    name: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            task_run = start_task_run(session, name, notes)
            run_id = task_run.id
    except ValueError as exc:
        return await _runs_with_error(request, str(exc))
    return RedirectResponse(f"/admin/runs/{run_id}", status_code=303)


@router.post("/runs/end", response_class=HTMLResponse)
async def end_run(request: Request) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = end_active_task_run(session)
        run_id = task_run.id if task_run else None
    if run_id is None:
        return RedirectResponse("/admin/runs", status_code=303)
    return RedirectResponse(f"/admin/runs/{run_id}", status_code=303)


@router.post("/runs/pause", response_class=HTMLResponse)
async def pause_run(request: Request) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = pause_active_task_run(session)
        run_id = task_run.id if task_run else None
    if run_id is None:
        return RedirectResponse("/admin/runs", status_code=303)
    return RedirectResponse(f"/admin/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/resume", response_class=HTMLResponse)
async def resume_run(request: Request, run_id: int) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            task_run = resume_task_run(session, run_id)
            resumed_run_id = task_run.id
    except (LookupError, ValueError):
        return RedirectResponse("/admin/runs", status_code=303)
    return RedirectResponse(f"/admin/runs/{resumed_run_id}", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, days: int = Query(30, ge=1, le=3650)) -> HTMLResponse:
    return RedirectResponse("/admin/settings/server", status_code=303)


@router.get("/settings/server", response_class=HTMLResponse)
async def settings_server(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_server.html", "server", days=days)


@router.get("/settings/routing", response_class=HTMLResponse)
async def settings_routing(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_routing.html", "routing", days=days)


@router.get("/settings/providers", response_class=HTMLResponse)
async def settings_providers(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_providers.html", "providers", days=days)


@router.get("/settings/pricing", response_class=HTMLResponse)
async def settings_pricing(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_pricing.html", "pricing", days=days)


@router.get("/settings/diagnostics", response_class=HTMLResponse)
async def settings_diagnostics(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_diagnostics.html", "diagnostics", days=days)


@router.get("/settings/data", response_class=HTMLResponse)
async def settings_data(
    request: Request,
    days: int = Query(30, ge=1, le=3650),
) -> HTMLResponse:
    return _settings_tab_response(request, "settings_data.html", "data", days=days)


def _settings_tab_response(
    request: Request,
    template_name: str,
    settings_tab: str,
    *,
    days: int = 30,
    error: str | None = None,
    test_result: dict[str, Any] | None = None,
    test_model: str = "gpt-test",
    test_prompt: str = TEST_PROMPT_DEFAULT,
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope(session_factory) as session:
        total = session.scalar(select(func.count()).select_from(RequestRecord)) or 0
        trim_count = session.scalar(
            select(func.count()).where(RequestRecord.created_at < cutoff)
        ) or 0
        context = _settings_context(
            request,
            session,
            total=total,
            trim_count=trim_count,
            days=days,
            error=error,
            test_result=test_result,
            test_model=test_model,
            test_prompt=test_prompt,
        )
        context.update(
            {
                "settings_tab": settings_tab,
                "active_nav": "settings",
                "app_version": "v0.5.0",
                "summary": _api_settings_summary(request, session, days=days),
                "fallback": get_fallback_summary(session),
                "provider_usage": get_provider_usage_summary(session),
                "route_usage": get_route_usage_summary(session),
                "health_results": getattr(request.app.state, "provider_health_results", {}),
                "storage_stats": _storage_stats(request, session),
            }
        )

    return templates.TemplateResponse(
        request,
        template_name,
        context,
    )


@router.post("/settings/incoming", response_class=HTMLResponse)
async def update_incoming(
    request: Request,
    incoming_port: int = Form(...),
    expose_all_ips: str | None = Form(None),
) -> HTMLResponse:
    if not 1 <= incoming_port <= 65535:
        return await _settings_with_error(request, "Incoming port must be between 1 and 65535.")

    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        set_incoming_server(session, incoming_port, expose_all_ips == "yes")
    return RedirectResponse("/admin/settings/server", status_code=303)


@router.post("/settings/upstream", response_class=HTMLResponse)
async def update_upstream(request: Request, upstream_url: str = Form(...)) -> HTMLResponse:
    try:
        normalized = normalize_upstream_url(upstream_url)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        set_setting(session, "upstream_url", normalized)
    return RedirectResponse("/admin/settings/server", status_code=303)


@router.post("/settings/upstream-defaults", response_class=HTMLResponse)
async def update_upstream_defaults(
    request: Request,
    upstream_url: str = Form(...),
    default_provider_slug: str = Form(""),
    default_model: str = Form(""),
    fallback_enabled: str | None = Form("yes"),
    return_to: str = Form("/admin/settings/server"),
) -> HTMLResponse:
    try:
        normalized = normalize_upstream_url(upstream_url)
        form = await request.form()
        fallback_values = {str(value) for value in form.getlist("fallback_enabled")}
        fallback_is_enabled = True if not fallback_values else "yes" in fallback_values
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            set_setting(session, "upstream_url", normalized)
            set_default_provider_slug(session, default_provider_slug or None)
            set_default_model(session, default_model)
            set_fallback_enabled(session, fallback_is_enabled)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse(_settings_fallback_return_path(return_to), status_code=303)


def _settings_fallback_return_path(value: str) -> str:
    return value if value in SETTINGS_FALLBACK_RETURN_PATHS else "/admin/settings/server"


@router.post("/settings/compat-fixes", response_class=HTMLResponse)
async def update_default_compat_fixes(request: Request, fixes: str = Form("")) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        parsed_fixes = normalize_fix_ids(fixes)
        with session_scope(session_factory) as session:
            set_default_compat_fixes(session, parsed_fixes)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/server", status_code=303)


@router.post("/settings/model-routes", response_class=HTMLResponse)
async def upsert_model_route(
    request: Request,
    model: str = Form(...),
    upstream_url: str = Form(...),
    upstream_model: str = Form(""),
    provider_slug: str = Form(""),
    api_key_env: str = Form(""),
    fixes: str = Form(""),
    match_type: str = Form("exact"),
    priority: int = Form(50),
    active: str | None = Form("yes"),
    override_fallback: str | None = Form(None),
    route_id: int | None = Form(None),
) -> HTMLResponse:
    settings = request.app.state.settings
    try:
        parsed_fixes = normalize_fix_ids(fixes)
        if not model.strip():
            raise ValueError("Model route model is required.")
        if model.strip() in {configured.model for configured in settings.model_routes}:
            raise ValueError("Model route already exists in startup configuration.")
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    session_factory: SessionFactory = request.app.state.session_factory
    form = await request.form()
    active_values = {str(value) for value in form.getlist("active")}
    route_active = True if not active_values else "yes" in active_values
    route_override_fallback = "yes" in {
        str(value) for value in form.getlist("override_fallback")
    }
    with session_scope(session_factory) as session:
        try:
            resolved_route_id = route_id
            if resolved_route_id is None:
                existing_route_id = session.scalar(
                    select(ModelRouteDB.id).where(
                        ModelRouteDB.incoming_model == model.strip(),
                        ModelRouteDB.match_type == match_type.strip().lower(),
                    )
                )
                resolved_route_id = int(existing_route_id) if existing_route_id else None
            upsert_model_route_db(
                session,
                route_id=resolved_route_id,
                incoming_model=model,
                match_type=match_type,
                upstream_url=upstream_url,
                upstream_model=upstream_model,
                provider_slug=provider_slug,
                api_key_env=api_key_env,
                compatibility_fixes=parsed_fixes,
                override_fallback=route_override_fallback,
                priority=priority,
                active=route_active,
            )
        except ValueError as exc:
            return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/routing", status_code=303)


@router.post("/settings/model-routes/delete", response_class=HTMLResponse)
async def delete_model_route(request: Request, model: str = Form("")) -> HTMLResponse:
    form = await request.form()
    route_id_value = form.get("route_id")
    if route_id_value:
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            if not delete_model_route_db(session, int(str(route_id_value))):
                return await _settings_with_error(request, "UI model route was not found.")
        return RedirectResponse("/admin/settings/routing", status_code=303)

    resolved_model = model.strip()
    settings = request.app.state.settings
    if resolved_model in {route.model for route in settings.model_routes}:
        return await _settings_with_error(
            request,
            "Startup configuration routes cannot be deleted from the UI.",
        )

    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_ui_model_route(session, resolved_model):
            return await _settings_with_error(request, "UI model route was not found.")
    return RedirectResponse("/admin/settings/routing", status_code=303)


@router.post("/settings/providers", response_class=HTMLResponse)
async def upsert_provider(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    upstream_url: str = Form(""),
    currency: str = Form("USD"),
    api_key_env: str = Form(""),
    active: str | None = Form("yes"),
    is_default_fallback: str | None = Form(None),
    capability_text: str | None = Form(None),
    capability_vision: str | None = Form(None),
    capability_tool_calling: str | None = Form(None),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    form = await request.form()
    active_values = {str(value) for value in form.getlist("active")}
    provider_active = True if not active_values else "yes" in active_values
    provider_is_default = "yes" in {
        str(value) for value in form.getlist("is_default_fallback")
    }
    try:
        with session_scope(session_factory) as session:
            upsert_model_provider(
                session,
                slug=slug,
                name=name,
                upstream_url=upstream_url,
                currency=currency,
                api_key_env=api_key_env,
                active=provider_active,
                is_default_fallback=provider_is_default,
                capabilities={
                    "text": capability_text == "yes",
                    "vision": capability_vision == "yes",
                    "tool_calling": capability_tool_calling == "yes",
                },
            )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/providers", status_code=303)


@router.post("/settings/providers/delete", response_class=HTMLResponse)
async def delete_provider(request: Request, slug: str = Form(...)) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            if not delete_model_provider(session, slug):
                return await _settings_with_error(request, "Provider was not found.")
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/providers", status_code=303)


@router.post("/settings/model-prices", response_class=HTMLResponse)
async def upsert_price(
    request: Request,
    provider_slug: str = Form(...),
    model: str = Form(...),
    display_name: str = Form(""),
    aliases: str = Form(""),
    input_usd_per_million: str = Form(...),
    cached_input_usd_per_million: str = Form(""),
    output_usd_per_million: str = Form(...),
    active: str | None = Form(None),
    notes: str = Form(""),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    form = await request.form()
    active_values = {str(value) for value in form.getlist("active")}
    price_active = True if not active_values else "yes" in active_values
    try:
        with session_scope(session_factory) as session:
            upsert_model_price(
                session,
                provider_slug=provider_slug,
                model=model,
                display_name=display_name,
                aliases=aliases,
                input_usd_per_million=input_usd_per_million,
                cached_input_usd_per_million=cached_input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
                active=price_active,
                notes=notes,
            )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/pricing", status_code=303)


@router.post("/settings/model-prices/delete", response_class=HTMLResponse)
async def delete_price(
    request: Request,
    provider_slug: str = Form(...),
    model: str = Form(...),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_model_price(session, provider_slug, model):
            return await _settings_with_error(request, "Model price was not found.")
    return RedirectResponse("/admin/settings/pricing", status_code=303)


@router.post("/settings/model-price-tiers", response_class=HTMLResponse)
async def upsert_price_tier(
    request: Request,
    model_price_id: int = Form(...),
    min_input_tokens: str = Form(""),
    max_input_tokens: str = Form(""),
    label: str = Form(""),
    input_usd_per_million: str = Form(...),
    cached_input_usd_per_million: str = Form(""),
    output_usd_per_million: str = Form(...),
    source_url: str = Form(""),
    checked_at: str = Form(""),
    release_date: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            upsert_model_price_tier(
                session,
                model_price_id=model_price_id,
                min_input_tokens=min_input_tokens,
                max_input_tokens=max_input_tokens,
                label=label,
                input_usd_per_million=input_usd_per_million,
                cached_input_usd_per_million=cached_input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
                source_url=source_url,
                checked_at=checked_at,
                release_date=release_date,
                notes=notes,
            )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings/pricing", status_code=303)


@router.post("/settings/model-price-tiers/delete", response_class=HTMLResponse)
async def delete_price_tier(
    request: Request,
    tier_id: int = Form(...),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_model_price_tier(session, tier_id):
            return await _settings_with_error(request, "Model price tier was not found.")
    return RedirectResponse("/admin/settings/pricing", status_code=303)


@router.post("/settings/test-upstream", response_class=HTMLResponse)
async def test_upstream(
    request: Request,
    test_kind: str = Form(...),
    model: str = Form("gpt-test"),
    prompt: str = Form(TEST_PROMPT_DEFAULT),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory

    try:
        payload = build_upstream_test_payload(test_kind, model, prompt)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    settings = request.app.state.settings
    request_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with session_scope(session_factory) as session:
        routing_decision = select_model_route(
            payload,
            settings,
            get_effective_model_routes(session, settings),
            session=session,
        )
        forward_body = build_forward_body(request_body, payload, routing_decision)
        forward_headers = build_forward_headers(
            {"content-type": "application/json"},
            routing_decision,
            set(),
        )
        upstream_url = routing_decision.upstream_base_url or get_upstream_url(session, settings)

    chat_url = f"{upstream_url.rstrip('/')}/chat/completions"
    result = await _send_upstream_test(
        chat_url,
        forward_body,
        forward_headers,
        test_kind,
        routing_decision.model_route,
        routing_decision.upstream_model,
    )

    return _settings_tab_response(
        request,
        "settings_diagnostics.html",
        "diagnostics",
        test_result=result,
        test_model=model.strip() or "gpt-test",
        test_prompt=prompt.strip() or TEST_PROMPT_DEFAULT,
    )


@router.post("/trim", response_class=HTMLResponse)
async def trim_records(
    request: Request,
    days: int = Form(...),
    confirm: str | None = Form(None),
) -> HTMLResponse:
    if days < 1:
        return await _settings_with_error(request, "Retention days must be at least 1.")
    if confirm != "yes":
        return await _settings_with_error(request, "Confirm deletion before trimming records.")

    session_factory: SessionFactory = request.app.state.session_factory
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope(session_factory) as session:
        records = session.scalars(
            select(RequestRecord).where(RequestRecord.created_at < cutoff)
        ).all()
        deleted = len(records)
        for record in records:
            session.delete(record)
    return RedirectResponse(f"/admin/settings/data?days={days}&trimmed={deleted}", status_code=303)


@router.get("/api/settings/summary", response_model=None)
async def api_settings_summary(request: Request, days: int = Query(30, ge=1, le=3650)):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return _api_settings_summary(request, session, days=days)


@router.post("/api/settings/listener", response_model=None)
async def api_update_listener(request: Request):
    payload = await _json_payload(request)
    port = int(payload.get("port") or payload.get("incoming_port") or 0)
    if not 1 <= port <= 65535:
        return JSONResponse({"detail": "Incoming port must be between 1 and 65535."}, 400)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        set_incoming_server(session, port, _truthy(payload.get("expose_all_ips")))
        return _api_settings_summary(request, session)


@router.post("/api/settings/upstream-defaults", response_model=None)
async def api_update_upstream_defaults(request: Request):
    payload = await _json_or_form_payload(request)
    try:
        normalized_url = normalize_upstream_url(str(payload.get("upstream_url", "")))
        provider_slug = str(payload.get("default_provider_slug") or "")
        default_model = str(payload.get("default_model") or "")
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            set_setting(session, "upstream_url", normalized_url)
            set_default_provider_slug(session, provider_slug or None)
            set_default_model(session, default_model)
            set_fallback_enabled(session, _truthy(payload.get("fallback_enabled", True)))
            return _api_settings_summary(request, session)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/api/settings/compat-fixes", response_model=None)
async def api_update_compat_fixes(request: Request):
    payload = await _json_or_form_payload(request)
    fixes = payload.get("fixes", payload.get("fix_ids", []))
    try:
        parsed = normalize_fix_ids(fixes)
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            set_default_compat_fixes(session, parsed)
        return {"compatibility_fixes": list(parsed)}
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.get("/api/settings/retention-preview", response_model=None)
async def api_retention_preview(request: Request, days: int = Query(30, ge=1, le=3650)):
    session_factory: SessionFactory = request.app.state.session_factory
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope(session_factory) as session:
        count = session.scalar(select(func.count()).where(RequestRecord.created_at < cutoff)) or 0
    return {"days": days, "rows": count}


@router.post("/api/settings/trim", response_model=None)
async def api_trim_records(request: Request):
    payload = await _json_payload(request)
    days = int(payload.get("days") or 0)
    if days < 1:
        return JSONResponse({"detail": "Retention days must be at least 1."}, status_code=400)
    if not _truthy(payload.get("confirm")):
        return JSONResponse({"detail": "Confirm deletion before trimming records."}, 400)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        records = session.scalars(
            select(RequestRecord).where(RequestRecord.created_at < cutoff)
        ).all()
        deleted = len(records)
        for record in records:
            session.delete(record)
    return {"deleted": deleted}


@router.post("/api/pricing/catalog/preview", response_model=None)
async def api_pricing_catalog_preview(request: Request):
    payload = await _json_payload(request)
    try:
        rows, options = await _pricing_catalog_rows(request, payload)
    except CatalogFetchError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return _pricing_catalog_preview(session, rows, options)


@router.post("/api/pricing/catalog/apply", response_model=None)
async def api_pricing_catalog_apply(request: Request):
    payload = await _json_payload(request)
    selected_keys = _pricing_catalog_selected_keys(payload)
    if not selected_keys:
        return JSONResponse({"detail": "Choose at least one catalog row to apply."}, 400)
    try:
        rows, options = await _pricing_catalog_rows(request, payload)
    except CatalogFetchError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    rows_by_key = {row.key: row for row in rows}
    missing_keys = [key for key in selected_keys if key not in rows_by_key]
    if missing_keys:
        return JSONResponse(
            {
                "detail": "Selected catalog rows are no longer available.",
                "missing_keys": missing_keys,
            },
            status_code=400,
        )

    session_factory: SessionFactory = request.app.state.session_factory
    counts: Counter[str] = Counter()
    with session_scope(session_factory) as session:
        for key in selected_keys:
            row = rows_by_key[key]
            status = _pricing_catalog_row_status(session, row)
            upsert_model_price(
                session,
                provider_slug=row.provider_slug,
                model=row.model,
                display_name=row.display_name,
                aliases=list(row.aliases),
                input_usd_per_million=row.input_usd_per_million,
                cached_input_usd_per_million=(
                    row.cached_input_usd_per_million
                    if row.cached_input_usd_per_million is not None
                    else ""
                ),
                output_usd_per_million=row.output_usd_per_million,
                active=True,
                source_url=row.source_url,
                checked_at=row.checked_at,
                notes=row.notes,
            )
            counts[status] += 1
        repriced_missing = (
            backfill_missing_cost_estimates(session)
            if _truthy_default(payload, "reprice_missing", True)
            else 0
        )
        preview = _pricing_catalog_preview(session, rows, options)
    return {
        "applied": len(selected_keys),
        "created": counts["new"],
        "updated": counts["update"],
        "unchanged": counts["unchanged"],
        "repriced_missing": repriced_missing,
        "preview": preview,
    }


@router.get("/api/providers", response_model=None)
async def api_list_providers(
    request: Request,
    search: str = "",
    status: str = "all",
    currency: str = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        providers = [
            _provider_api_row(session, provider)
            for provider in list_model_providers(session)
        ]
    rows = _filter_providers(providers, search=search, status=status, currency=currency)
    return _paginated(rows, page, per_page)


@router.post("/api/providers", response_model=None)
async def api_create_provider(request: Request):
    payload = await _json_payload(request)
    return _save_provider_from_payload(request, payload)


@router.post("/api/providers/health-checks", response_model=None)
async def api_provider_health_checks(request: Request):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        providers = [provider for provider in list_model_providers(session) if provider.active]
    results = [await _provider_health_result(provider) for provider in providers]
    request.app.state.provider_health_results = {row["provider_slug"]: row for row in results}
    return results


@router.get("/api/providers/usage", response_model=None)
async def api_provider_usage(request: Request):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return get_provider_usage_summary(session)


@router.get("/api/providers/{slug}", response_model=None)
async def api_get_provider(request: Request, slug: str):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        provider = session.get(ModelProvider, slug)
        if provider is None:
            return JSONResponse({"detail": "Provider not found."}, status_code=404)
        return _provider_api_row(session, provider)


@router.put("/api/providers/{slug}", response_model=None)
async def api_update_provider(request: Request, slug: str):
    payload = await _json_payload(request)
    payload["slug"] = slug
    return _save_provider_from_payload(request, payload)


@router.delete("/api/providers/{slug}", response_model=None)
async def api_delete_provider(request: Request, slug: str):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_model_provider(session, slug):
            return JSONResponse({"detail": "Provider not found."}, status_code=404)
    return {"deleted": True}


@router.post("/api/providers/{slug}/test", response_model=None)
async def api_test_provider(request: Request, slug: str):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        provider = session.get(ModelProvider, slug)
        if provider is None:
            return JSONResponse({"detail": "Provider not found."}, status_code=404)
        return await _provider_health_result(provider)


@router.get("/api/routes", response_model=None)
async def api_list_routes(
    request: Request,
    search: str = "",
    status: str = "all",
    provider: str = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        rows = [_route_api_row(session, route) for route in list_model_routes_db(session)]
    filtered = _filter_routes(rows, search=search, status=status, provider=provider)
    return _paginated(filtered, page, per_page)


@router.post("/api/routes", response_model=None)
async def api_create_route(request: Request):
    payload = await _json_payload(request)
    return _save_route_from_payload(request, payload)


@router.post("/api/routes/defaults/preview", response_model=None)
async def api_preview_default_routes(request: Request):
    payload = await _json_payload(request)
    provider_slug = str(payload.get("provider_slug") or payload.get("provider") or "").strip()
    mode = str(payload.get("mode") or "missing_only")
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        try:
            return preview_default_model_routes(
                session,
                provider_slug=provider_slug or None,
                mode=mode,
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/api/routes/defaults/apply", response_model=None)
async def api_apply_default_routes(request: Request):
    payload = await _json_payload(request)
    provider_slug = str(payload.get("provider_slug") or payload.get("provider") or "").strip()
    mode = str(payload.get("mode") or "missing_only")
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        try:
            return apply_default_model_routes(
                session,
                provider_slug=provider_slug or None,
                mode=mode,
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/api/routes/sample-request", response_model=None)
async def api_route_sample_request(request: Request):
    payload = await _json_payload(request)
    model = str(payload.get("model") or payload.get("incoming_model") or "").strip()
    provider_slug = str(payload.get("provider_slug") or payload.get("provider") or "").strip()
    if not model:
        return JSONResponse({"detail": "Model is required."}, status_code=400)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        try:
            return _route_sample_request(
                request,
                session,
                model,
                provider_slug=provider_slug or None,
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/api/routes/simulate", response_model=None)
async def api_simulate_route(request: Request):
    payload = await _json_payload(request)
    incoming_model = str(payload.get("incoming_model") or payload.get("model") or "").strip()
    if not incoming_model:
        return JSONResponse({"detail": "Incoming model is required."}, status_code=400)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        result = simulate_route_resolution(incoming_model, session, request.app.state.settings)
        sample = _route_sample_request(request, session, incoming_model)
    return {
        "status": result.status,
        "matched_route": result.matched_route,
        "match_type": result.match_type,
        "upstream_url": result.upstream_url,
        "upstream_model": result.upstream_model,
        "provider_slug": result.provider_slug,
        "provider_name": result.provider_name,
        "api_key_state": result.api_key_state,
        "compatibility_fixes": list(result.compatibility_fixes),
        "sample_request": sample,
    }


@router.get("/api/routes/usage", response_model=None)
async def api_route_usage(request: Request):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return get_route_usage_summary(session)


@router.get("/api/routes/{route_id}", response_model=None)
async def api_get_route(request: Request, route_id: int):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        route = get_model_route_db(session, route_id)
        if route is None:
            return JSONResponse({"detail": "Route not found."}, status_code=404)
        return _route_api_row(session, route)


@router.put("/api/routes/{route_id}", response_model=None)
async def api_update_route(request: Request, route_id: int):
    payload = await _json_payload(request)
    payload["id"] = route_id
    return _save_route_from_payload(request, payload)


@router.delete("/api/routes/{route_id}", response_model=None)
async def api_delete_route(request: Request, route_id: int):
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_model_route_db(session, route_id):
            return JSONResponse({"detail": "Route not found."}, status_code=404)
    return {"deleted": True}


@router.post("/api/routes/{route_id}/test", response_model=None)
async def api_test_route(request: Request, route_id: int):
    payload = await _json_payload(request)
    test_kind = str(payload.get("test_kind") or payload.get("message_type") or "simple")
    prompt = str(payload.get("prompt") or TEST_PROMPT_DEFAULT)
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        route = get_model_route_db(session, route_id)
        if route is None:
            return JSONResponse({"detail": "Route not found."}, status_code=404)
        test_payload = build_upstream_test_payload(test_kind, route.incoming_model, prompt)
        decision = select_model_route(test_payload, request.app.state.settings, session=session)
        body = json.dumps(test_payload, ensure_ascii=False, separators=(",", ":")).encode()
        forward_body = build_forward_body(body, test_payload, decision)
        forward_headers = build_forward_headers(
            {"content-type": "application/json"},
            decision,
            set(),
        )
        upstream_base = (decision.upstream_base_url or route.upstream_url).rstrip("/")
        chat_url = f"{upstream_base}/chat/completions"
    return await _send_upstream_test(
        chat_url,
        forward_body,
        forward_headers,
        test_kind,
        decision.model_route,
        decision.upstream_model,
    )


def build_upstream_test_payload(test_kind: str, model: str, prompt: str) -> dict[str, Any]:
    resolved_model = model.strip() or "gpt-test"
    resolved_prompt = prompt.strip() or TEST_PROMPT_DEFAULT
    if test_kind == "simple":
        return {
            "model": resolved_model,
            "messages": [{"role": "user", "content": resolved_prompt}],
        }
    if test_kind == "image":
        return {
            "model": resolved_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": resolved_prompt},
                        {"type": "image_url", "image_url": {"url": TEST_IMAGE_DATA_URL}},
                    ],
                }
            ],
        }
    if test_kind == "tools":
        return {
            "model": resolved_model,
            "messages": [{"role": "user", "content": resolved_prompt}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Return the current weather for a city.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "City and country, such as Paris, France.",
                                }
                            },
                            "required": ["location"],
                        },
                    },
                }
            ],
        }
    raise ValueError("Choose a valid upstream test: simple, image, or function call.")


def _route_sample_request(
    request: Request,
    session,
    model: str,
    *,
    provider_slug: str | None = None,
) -> dict[str, object]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello through the proxy"}],
    }
    decision = _sample_routing_decision(request, session, payload, provider_slug=provider_slug)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    forward_body = build_forward_body(body, payload, decision)
    try:
        forward_payload: object = json.loads(forward_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        forward_payload = forward_body.decode("utf-8", errors="replace")

    port = get_incoming_port(session, request.app.state.settings)
    client_base_url = f"http://localhost:{port}/v1"
    endpoint_url = f"{client_base_url}/chat/completions"
    request_json = json.dumps(payload, ensure_ascii=False, indent=2)
    curl = (
        "curl "
        f"{endpoint_url} "
        "-H 'Content-Type: application/json' "
        "-H 'Authorization: Bearer local-dev-key' "
        f"-d '{request_json}'"
    )
    python = (
        "from openai import OpenAI\n\n"
        "client = OpenAI(api_key=\"local-dev-key\", "
        f"base_url=\"{client_base_url}\")\n"
        "response = client.chat.completions.create(\n"
        f"    model={model!r},\n"
        "    messages=[{\"role\": \"user\", \"content\": \"Hello through the proxy\"}],\n"
        ")\n"
        "print(response.choices[0].message.content)"
    )
    upstream_url = decision.upstream_base_url
    auth_hint = (
        f"Bearer ${decision.api_key_env}"
        if decision.api_key_env
        else "Preserves client Authorization header when present"
    )
    return {
        "model": model,
        "provider_slug": decision.provider_slug,
        "route": decision.model_route,
        "client_base_url": client_base_url,
        "curl": curl,
        "python": python,
        "upstream_preview": {
            "url": f"{upstream_url.rstrip('/')}/chat/completions" if upstream_url else None,
            "headers": {"authorization": auth_hint, "content-type": "application/json"},
            "body": forward_payload,
        },
    }


def _sample_routing_decision(
    request: Request,
    session,
    payload: dict[str, object],
    *,
    provider_slug: str | None = None,
) -> RoutingDecision:
    if not provider_slug:
        return select_model_route(payload, request.app.state.settings, session=session)

    provider = session.get(ModelProvider, provider_slug)
    if provider is None:
        raise ValueError("Provider was not found.")
    model = str(payload.get("model") or "")
    candidate = next(
        (
            candidate
            for candidate in build_default_model_route_candidates(
                session,
                provider_slug=provider_slug,
            )
            if candidate.incoming_model == model
        ),
        None,
    )
    upstream_model = candidate.upstream_model if candidate else model
    upstream_url = candidate.upstream_url if candidate else provider.upstream_url
    if not upstream_url:
        raise ValueError("Provider has no upstream URL.")
    route = ResolvedRoute(
        incoming_model=model,
        match_type="exact",
        upstream_url=upstream_url,
        upstream_model=upstream_model,
        provider_slug=provider.slug,
        api_key_env=provider.api_key_env,
        priority=90,
        source="sample",
    )
    return RoutingDecision(
        requested_model=model,
        resolved_route=route,
        match_type="exact",
        match_source="sample",
    )


async def _send_upstream_test(
    chat_url: str,
    body: bytes,
    headers: dict[str, str],
    test_kind: str,
    model_route: str | None,
    upstream_model: str | None,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(chat_url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        return {
            "kind": test_kind,
            "url": chat_url,
            "ok": False,
            "error": str(exc),
            "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
            "model_route": model_route,
            "upstream_model": upstream_model,
        }

    body = response.text
    try:
        body = json.dumps(response.json(), indent=2)
    except json.JSONDecodeError:
        pass
    return {
        "kind": test_kind,
        "url": chat_url,
        "ok": response.is_success,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
        "body": body[:6000],
        "model_route": model_route,
        "upstream_model": upstream_model,
    }


async def _json_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


async def _json_or_form_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await _json_payload(request)
    form = await request.form()
    return dict(form)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _truthy_default(payload: dict[str, Any], key: str, default: bool) -> bool:
    if key not in payload:
        return default
    return _truthy(payload.get(key))


async def _pricing_catalog_rows(
    request: Request,
    payload: dict[str, Any],
) -> tuple[list[PricingCatalogRow], dict[str, object]]:
    source = str(payload.get("source") or "huggingface-router").strip()
    search = str(payload.get("search") or "").strip()
    try:
        limit = int(payload.get("limit") or 25)
    except (TypeError, ValueError):
        limit = 25
    include_base_rows = _truthy_default(payload, "include_base_rows", True)
    include_provider_rows = _truthy_default(payload, "include_provider_rows", True)
    api_key = _pricing_catalog_api_key(request, source)
    rows = await fetch_catalog_rows(
        request.app.state.http_client,
        source=source,
        search=search,
        limit=limit,
        include_base_rows=include_base_rows,
        include_provider_rows=include_provider_rows,
        api_key=api_key,
    )
    options = {
        "source": source,
        "search": search,
        "limit": max(1, min(limit, 100)),
        "include_base_rows": include_base_rows,
        "include_provider_rows": include_provider_rows,
    }
    return rows, options


def _pricing_catalog_api_key(request: Request, source: str) -> str | None:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        provider = session.get(ModelProvider, source)
        if provider is None:
            raise CatalogFetchError("Catalog source provider is not configured.")
        env_name = provider.api_key_env
    if not env_name:
        return None
    value = os.getenv(env_name)
    return value.strip() if value and value.strip() else None


def _pricing_catalog_selected_keys(payload: dict[str, Any]) -> list[str]:
    values = payload.get("keys", payload.get("selected_keys", []))
    if isinstance(values, str):
        candidates = [chunk.strip() for chunk in values.splitlines() for chunk in chunk.split(",")]
    elif isinstance(values, list):
        candidates = [str(value).strip() for value in values]
    else:
        candidates = []
    selected: list[str] = []
    for key in candidates:
        if key and key not in selected:
            selected.append(key)
    return selected


def _pricing_catalog_preview(
    session,
    rows: list[PricingCatalogRow],
    options: dict[str, object],
) -> dict[str, object]:
    items = [
        _pricing_catalog_row_payload(row, _pricing_catalog_row_status(session, row))
        for row in rows
    ]
    counts = Counter(str(item["status"]) for item in items)
    return {
        **options,
        "items": items,
        "total": len(items),
        "counts": {
            "new": counts["new"],
            "update": counts["update"],
            "unchanged": counts["unchanged"],
        },
    }


def _pricing_catalog_row_status(session, row: PricingCatalogRow) -> str:
    existing = session.scalar(
        select(ModelPrice).where(
            ModelPrice.provider_slug == row.provider_slug,
            ModelPrice.model == row.model,
        )
    )
    if existing is None:
        return "new"
    if not existing.active:
        return "update"
    comparisons = (
        existing.display_name == (row.display_name or None),
        tuple(_model_price_aliases(existing)) == tuple(row.aliases),
        existing.input_usd_per_million == row.input_usd_per_million,
        existing.cached_input_usd_per_million == row.cached_input_usd_per_million,
        existing.output_usd_per_million == row.output_usd_per_million,
        (existing.source_url or "") == (row.source_url or ""),
        (existing.checked_at or "") == (row.checked_at or ""),
        (existing.notes or "") == (row.notes or ""),
    )
    return "unchanged" if all(comparisons) else "update"


def _pricing_catalog_row_payload(row: PricingCatalogRow, status: str) -> dict[str, object]:
    return {
        "key": row.key,
        "source": row.source,
        "provider_slug": row.provider_slug,
        "model": row.model,
        "display_name": row.display_name,
        "aliases": list(row.aliases),
        "input_usd_per_million": str(row.input_usd_per_million),
        "cached_input_usd_per_million": (
            str(row.cached_input_usd_per_million)
            if row.cached_input_usd_per_million is not None
            else None
        ),
        "output_usd_per_million": str(row.output_usd_per_million),
        "source_url": row.source_url,
        "checked_at": row.checked_at,
        "notes": row.notes,
        "row_kind": row.row_kind,
        "external_provider": row.external_provider,
        "context_length": row.context_length,
        "supports_tools": row.supports_tools,
        "status": status,
        "selected": status in {"new", "update"},
        "display": {
            "input_usd_per_million": format_usd(row.input_usd_per_million),
            "cached_input_usd_per_million": format_usd(row.cached_input_usd_per_million),
            "output_usd_per_million": format_usd(row.output_usd_per_million),
            "context_length": format_compact_number(row.context_length),
            "supports_tools": (
                "Yes" if row.supports_tools else "No" if row.supports_tools is False else "-"
            ),
        },
    }


def _model_price_aliases(price: ModelPrice) -> list[str]:
    if not price.aliases_json:
        return []
    try:
        aliases = json.loads(price.aliases_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(aliases, list):
        return []
    return [alias for alias in aliases if isinstance(alias, str)]


def _optional_query_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field_name} must be an integer.") from None


def _api_settings_summary(request: Request, session, *, days: int = 30) -> dict[str, object]:
    settings = request.app.state.settings
    host = get_incoming_host(session, settings)
    port = get_incoming_port(session, settings)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    fallback = get_fallback_summary(session)
    return {
        "listener": {"host": host, "port": port},
        "client_base_url": f"http://localhost:{port}/v1",
        "upstream": {
            "url": get_upstream_url(session, settings),
            "default_provider_slug": fallback["provider_slug"],
            "default_provider_name": fallback["provider_name"],
            "default_model": fallback["model"],
        },
        "stored_rows": session.scalar(select(func.count()).select_from(RequestRecord)) or 0,
        "active_routes": session.scalar(
            select(func.count()).where(ModelRouteDB.active.is_(True))
        )
        or 0,
        "active_providers": session.scalar(
            select(func.count()).where(ModelProvider.active.is_(True))
        )
        or 0,
        "retention_days": days,
        "rows_older_than_retention": session.scalar(
            select(func.count()).where(RequestRecord.created_at < cutoff)
        )
        or 0,
    }


def _provider_api_row(session, provider: ModelProvider) -> dict[str, object]:
    route_count = session.scalar(
        select(func.count()).where(ModelRouteDB.provider_slug == provider.slug)
    ) or 0
    model_count = session.scalar(
        select(func.count()).where(ModelPrice.provider_slug == provider.slug)
    ) or 0
    try:
        capabilities = json.loads(provider.capabilities_json or "{}")
    except json.JSONDecodeError:
        capabilities = {}
    return {
        "slug": provider.slug,
        "name": provider.name,
        "upstream_url": provider.upstream_url,
        "base_url": provider.upstream_url,
        "currency": provider.currency,
        "api_key_env": provider.api_key_env,
        "active": bool(provider.active),
        "status": "active" if provider.active else "inactive",
        "is_default_fallback": bool(provider.is_default_fallback),
        "capabilities": capabilities,
        "model_count": model_count,
        "route_count": route_count,
    }


def _route_api_row(session, route: ModelRouteDB) -> dict[str, object]:
    provider = session.get(ModelProvider, route.provider_slug) if route.provider_slug else None
    return {
        "id": route.id,
        "incoming_model": route.incoming_model,
        "match_type": route.match_type,
        "upstream_url": route.upstream_url,
        "upstream_model": route.effective_upstream_model,
        "provider_slug": route.provider_slug,
        "provider_name": provider.name if provider else None,
        "api_key_env": route.api_key_env,
        "compatibility_fixes": list(route.fixes),
        "override_fallback": bool(route.override_fallback),
        "priority": route.priority,
        "active": bool(route.active),
        "status": "active" if route.active else "inactive",
        "managed_by": route.managed_by,
        "managed": route.managed_by == DEFAULT_ROUTE_SEED_OWNER,
    }


def _filter_providers(
    rows: list[dict[str, object]],
    *,
    search: str,
    status: str,
    currency: str,
) -> list[dict[str, object]]:
    needle = search.strip().lower()
    filtered = rows
    if needle:
        filtered = [
            row
            for row in filtered
            if needle
            in " ".join(
                str(row.get(key) or "").lower()
                for key in ("slug", "name", "upstream_url", "currency")
            )
        ]
    if status in {"active", "inactive"}:
        filtered = [row for row in filtered if row["status"] == status]
    if currency:
        filtered = [row for row in filtered if row["currency"] == currency]
    return filtered


def _filter_routes(
    rows: list[dict[str, object]],
    *,
    search: str,
    status: str,
    provider: str,
) -> list[dict[str, object]]:
    needle = search.strip().lower()
    filtered = rows
    if needle:
        filtered = [
            row
            for row in filtered
            if needle
            in " ".join(
                str(row.get(key) or "").lower()
                for key in ("incoming_model", "upstream_url", "upstream_model", "provider_name")
            )
        ]
    if status in {"active", "inactive"}:
        filtered = [row for row in filtered if row["status"] == status]
    if provider:
        filtered = [row for row in filtered if row["provider_slug"] == provider]
    return filtered


def _paginated(rows: list[dict[str, object]], page: int, per_page: int) -> dict[str, object]:
    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": rows[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, math.ceil(total / per_page)) if total else 1,
    }


def _save_provider_from_payload(request: Request, payload: dict[str, Any]):
    try:
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            provider = upsert_model_provider(
                session,
                slug=str(payload.get("slug") or ""),
                name=str(payload.get("name") or ""),
                upstream_url=str(payload.get("upstream_url") or payload.get("base_url") or ""),
                currency=str(payload.get("currency") or "USD"),
                api_key_env=str(payload.get("api_key_env") or ""),
                active=_truthy(payload.get("active", True)),
                is_default_fallback=_truthy(payload.get("is_default_fallback")),
                capabilities=payload.get("capabilities"),
            )
            if _truthy(payload.get("is_default_fallback")):
                set_default_provider_slug(session, provider.slug)
            return _provider_api_row(session, provider)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


def _save_route_from_payload(request: Request, payload: dict[str, Any]):
    try:
        session_factory: SessionFactory = request.app.state.session_factory
        with session_scope(session_factory) as session:
            route = upsert_model_route_db(
                session,
                route_id=int(payload["id"]) if payload.get("id") else None,
                incoming_model=str(payload.get("incoming_model") or payload.get("model") or ""),
                match_type=str(payload.get("match_type") or "exact"),
                upstream_url=str(payload.get("upstream_url") or ""),
                upstream_model=str(payload.get("upstream_model") or ""),
                provider_slug=str(payload.get("provider_slug") or ""),
                api_key_env=str(payload.get("api_key_env") or ""),
                compatibility_fixes=payload.get("compatibility_fixes") or payload.get("fixes"),
                override_fallback=_truthy(payload.get("override_fallback")),
                priority=payload.get("priority", 50),
                active=_truthy(payload.get("active", True)),
            )
            return _route_api_row(session, route)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


async def _provider_health_result(provider: ModelProvider) -> dict[str, object]:
    if not provider.upstream_url:
        return {
            "provider_slug": provider.slug,
            "status": "warning",
            "latency_ms": None,
            "auth_state": "not_configured",
            "message": "Provider has no base URL.",
        }
    headers = {}
    auth_state = "not_configured"
    if provider.api_key_env:
        token = os.getenv(provider.api_key_env)
        auth_state = "valid" if token else "missing_key"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    started = datetime.now(UTC)
    url = f"{provider.upstream_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        status = (
            "healthy"
            if response.status_code < 500 and auth_state != "missing_key"
            else "warning"
        )
        return {
            "provider_slug": provider.slug,
            "status": status,
            "latency_ms": latency_ms,
            "auth_state": auth_state,
            "message": f"HTTP {response.status_code}",
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    except httpx.HTTPError as exc:
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return {
            "provider_slug": provider.slug,
            "status": "warning",
            "latency_ms": latency_ms,
            "auth_state": auth_state,
            "message": str(exc),
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }


def _settings_context(
    request: Request,
    session,
    *,
    total: int,
    trim_count: int,
    days: int,
    error: str | None = None,
    test_result: dict[str, Any] | None = None,
    test_model: str = "gpt-test",
    test_prompt: str = TEST_PROMPT_DEFAULT,
) -> dict[str, Any]:
    settings = request.app.state.settings
    providers = list_model_providers(session)
    default_fixes = get_default_compat_fixes(session, settings)
    fallback = get_fallback_summary(session)
    return {
        "upstream_url": get_upstream_url(session, settings),
        "model_routes": _settings_model_route_rows(session, settings, providers),
        "default_compat_fixes": default_fixes,
        "default_compat_fixes_text": fix_ids_text(default_fixes),
        "available_compat_fixes": compatibility_fix_rows(),
        "providers": [_provider_row(provider) for provider in providers],
        "model_prices": [_model_price_row(price) for price in list_model_prices(session)],
        "default_provider_slug": fallback["provider_slug"] or "",
        "default_model": fallback["model"] or "",
        "fallback_enabled": bool(fallback["enabled"]),
        "incoming_host": get_incoming_host(session, settings),
        "incoming_port": get_incoming_port(session, settings),
        "expose_all_ips": get_expose_all_ips(session, settings),
        "days": days,
        "total": total,
        "trim_count": trim_count,
        "error": error,
        "test_result": test_result,
        "test_model": test_model,
        "test_prompt": test_prompt,
        "page_title": "Settings",
    }


def _settings_model_route_rows(session, settings, providers) -> list[dict[str, object]]:
    provider_names = {provider.slug: provider.name for provider in providers}
    rows: list[dict[str, object]] = []
    for route in settings.model_routes:
        row = model_route_display(route)
        row["source"] = "startup"
        row["editable"] = False
        row["provider_name"] = provider_names.get(route.provider_slug or "")
        row["fixes_text"] = fix_ids_text(route.fixes)
        rows.append(row)
    for route in list_model_routes_db(session):
        row = model_route_display(route)
        row["source"] = "seeded" if route.managed_by == DEFAULT_ROUTE_SEED_OWNER else "ui"
        row["editable"] = True
        row["provider_name"] = provider_names.get(route.provider_slug or "")
        row["fixes_text"] = fix_ids_text(route.fixes)
        rows.append(row)
    return rows


def _provider_row(provider) -> dict[str, object]:
    try:
        capabilities = json.loads(provider.capabilities_json or "{}")
    except json.JSONDecodeError:
        capabilities = {}
    return {
        "slug": provider.slug,
        "name": provider.name,
        "upstream_url": provider.upstream_url,
        "currency": provider.currency,
        "api_key_env": provider.api_key_env,
        "active": bool(provider.active),
        "is_default_fallback": bool(provider.is_default_fallback),
        "capabilities": capabilities,
    }


def _storage_stats(request: Request, session) -> dict[str, object]:
    settings = request.app.state.settings
    oldest = session.scalar(select(func.min(RequestRecord.created_at)))
    newest = session.scalar(select(func.max(RequestRecord.created_at)))
    database_url = settings.database_url
    db_path: Path | None = None
    db_file_size = None
    if database_url.startswith("sqlite:///"):
        raw_path = unquote(database_url.removeprefix("sqlite:///"))
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        db_path = candidate.resolve()
        if db_path.exists():
            db_file_size = db_path.stat().st_size
    return {
        "database_url": database_url,
        "database_path": str(db_path) if db_path else None,
        "database_file_size": db_file_size,
        "oldest_record_at": oldest.isoformat().replace("+00:00", "Z")
        if isinstance(oldest, datetime)
        else None,
        "newest_record_at": newest.isoformat().replace("+00:00", "Z")
        if isinstance(newest, datetime)
        else None,
    }


def _model_price_row(price) -> dict[str, object]:
    aliases: list[str] = []
    if price.aliases_json:
        try:
            value = json.loads(price.aliases_json)
        except json.JSONDecodeError:
            value = []
        if isinstance(value, list):
            aliases = [item for item in value if isinstance(item, str)]
    return {
        "id": price.id,
        "provider_slug": price.provider_slug,
        "provider_name": price.provider.name,
        "model": price.model,
        "display_name": price.display_name,
        "aliases": ", ".join(aliases),
        "input_usd_per_million": price.input_usd_per_million,
        "cached_input_usd_per_million": price.cached_input_usd_per_million,
        "output_usd_per_million": price.output_usd_per_million,
        "active": price.active,
        "source_url": price.source_url,
        "checked_at": price.checked_at,
        "release_date": price.release_date,
        "notes": price.notes,
        "tiers": [_model_price_tier_row(tier) for tier in price.tiers],
    }


def _model_price_tier_row(tier) -> dict[str, object]:
    return {
        "id": tier.id,
        "label": tier.label,
        "range": _tier_range_label(tier.min_input_tokens, tier.max_input_tokens),
        "min_input_tokens": tier.min_input_tokens,
        "max_input_tokens": tier.max_input_tokens,
        "input_usd_per_million": tier.input_usd_per_million,
        "cached_input_usd_per_million": tier.cached_input_usd_per_million,
        "output_usd_per_million": tier.output_usd_per_million,
        "source_url": tier.source_url,
        "checked_at": tier.checked_at,
        "release_date": tier.release_date,
        "notes": tier.notes,
    }


def _tier_range_label(min_input_tokens: int | None, max_input_tokens: int | None) -> str:
    lower = min_input_tokens if min_input_tokens is not None else 0
    if max_input_tokens is None:
        return f"{lower:,}+ input tokens"
    return f"{lower:,}-{max_input_tokens - 1:,} input tokens"


def _run_what_if_context(
    usages: list[ExtractedTokenUsage],
    session,
    *,
    requested_keys: list[str] | None,
    baseline: dict[str, object] | None = None,
) -> dict[str, object]:
    active_prices = [price for price in list_model_prices(session) if price.active]
    price_by_key = {_model_price_key(price): price for price in active_prices}
    selected_keys = _selected_run_what_if_keys(requested_keys, price_by_key)
    selected_key_set = set(selected_keys)
    scenarios = [
        _run_cost_estimate_row(estimate_run_cost(usages, price_by_key[key]))
        for key in selected_keys
        if key in price_by_key
    ]

    message = None
    if not active_prices:
        message = "No active model prices are configured."
    elif requested_keys and not scenarios:
        message = "No active model prices matched the selected comparison."
    elif not requested_keys and not scenarios:
        message = "Default comparison prices are not configured. Choose active prices to compare."

    return {
        "options": [
            _run_what_if_option(price, checked=_model_price_key(price) in selected_key_set)
            for price in active_prices
        ],
        "baseline": baseline,
        "scenarios": scenarios,
        "selected_keys": selected_keys,
        "compared_count": len(scenarios),
        "message": message,
    }


def _run_current_cost_baseline(session, run_id: int) -> dict[str, object] | None:
    row = session.execute(
        select(
            func.sum(RequestRecord.billing_total_cost_usd),
            func.count(RequestRecord.billing_total_cost_usd),
        ).where(RequestRecord.task_run_id == run_id)
    ).one()
    if not row[1]:
        return None
    providers = [
        value
        for value in session.scalars(
            select(
                func.coalesce(
                    RequestRecord.billing_provider_name,
                    RequestRecord.billing_provider_slug,
                )
            )
            .where(
                RequestRecord.task_run_id == run_id,
                or_(
                    RequestRecord.billing_provider_name.is_not(None),
                    RequestRecord.billing_provider_slug.is_not(None),
                ),
            )
            .distinct()
            .order_by(
                func.coalesce(
                    RequestRecord.billing_provider_name,
                    RequestRecord.billing_provider_slug,
                )
            )
        ).all()
        if value
    ]
    models = [
        value
        for value in session.scalars(
            select(func.coalesce(RequestRecord.billing_model, RequestRecord.model))
            .where(
                RequestRecord.task_run_id == run_id,
                or_(
                    RequestRecord.billing_model.is_not(None),
                    RequestRecord.model.is_not(None),
                ),
            )
            .distinct()
            .order_by(func.coalesce(RequestRecord.billing_model, RequestRecord.model))
        ).all()
        if value
    ]
    provider_name = providers[0] if len(providers) == 1 else "Captured providers"
    model = models[0] if len(models) == 1 else "Captured models"
    total_cost = row[0]
    return {
        "label": "Current run",
        "provider_name": provider_name,
        "model": model,
        "total_cost_usd": _json_safe_number(total_cost),
        "display": {
            "total_cost_usd": format_usd(total_cost),
        },
    }


def _selected_run_what_if_keys(
    requested_keys: list[str] | None,
    price_by_key: dict[str, ModelPrice],
) -> list[str]:
    source_keys = requested_keys if requested_keys else list(DEFAULT_RUN_WHAT_IF_KEYS)
    selected: list[str] = []
    for value in source_keys:
        key = value.strip()
        if not key or key in selected or key not in price_by_key:
            continue
        selected.append(key)
    return selected


def _run_what_if_option(price: ModelPrice, *, checked: bool) -> dict[str, object]:
    key = _model_price_key(price)
    label = price.display_name or price.model
    return {
        "key": key,
        "provider_slug": price.provider_slug,
        "provider_name": price.provider.name,
        "model": price.model,
        "display_name": price.display_name,
        "label": label,
        "search_text": " ".join(
            part
            for part in (label, price.provider.name, price.provider_slug, price.model)
            if part
        ),
        "checked": checked,
    }


def _run_cost_estimate_row(estimate: RunCostEstimate) -> dict[str, object]:
    mixed_rate_display = "Mixed tiers"
    input_rate_display = (
        mixed_rate_display
        if estimate.mixed_tiers
        else format_usd(estimate.input_usd_per_million)
    )
    cached_input_rate_display = (
        mixed_rate_display
        if estimate.mixed_tiers
        else format_usd(estimate.cached_input_usd_per_million)
    )
    output_rate_display = (
        mixed_rate_display
        if estimate.mixed_tiers
        else format_usd(estimate.output_usd_per_million)
    )
    return {
        "key": f"{estimate.provider_slug}:{estimate.model}",
        "provider_name": estimate.provider_name,
        "model": estimate.model,
        "display_name": estimate.display_name,
        "label": estimate.display_name or estimate.model,
        "input_usd_per_million": _json_safe_number(estimate.input_usd_per_million),
        "cached_input_usd_per_million": _json_safe_number(
            estimate.cached_input_usd_per_million
        ),
        "output_usd_per_million": _json_safe_number(estimate.output_usd_per_million),
        "mixed_tiers": estimate.mixed_tiers,
        "input_tokens": estimate.input_tokens,
        "cached_input_tokens": estimate.cached_input_tokens,
        "cache_write_input_tokens": estimate.cache_write_input_tokens,
        "output_tokens": estimate.output_tokens,
        "total_tokens": estimate.total_tokens,
        "input_cost_usd": _json_safe_number(estimate.input_cost_usd),
        "cached_input_cost_usd": _json_safe_number(estimate.cached_input_cost_usd),
        "output_cost_usd": _json_safe_number(estimate.output_cost_usd),
        "total_cost_usd": _json_safe_number(estimate.total_cost_usd),
        "included_request_count": estimate.included_request_count,
        "missing_usage_request_count": estimate.missing_usage_request_count,
        "notes": estimate.notes,
        "display": {
            "input_tokens": format_compact_number(estimate.input_tokens),
            "cached_input_tokens": format_compact_number(estimate.cached_input_tokens),
            "output_tokens": format_compact_number(estimate.output_tokens),
            "input_usd_per_million": input_rate_display,
            "cached_input_usd_per_million": cached_input_rate_display,
            "output_usd_per_million": output_rate_display,
            "input_cost_usd": format_usd(estimate.input_cost_usd),
            "output_cost_usd": format_usd(estimate.output_cost_usd),
            "total_cost_usd": format_usd(estimate.total_cost_usd),
            "included_request_count": format_compact_number(
                estimate.included_request_count
            ),
            "missing_usage_request_count": format_compact_number(
                estimate.missing_usage_request_count
            ),
        },
    }


def _json_safe_number(value: object) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return float(value)
    return None


def _model_price_key(price: ModelPrice) -> str:
    return f"{price.provider_slug}:{price.model}"


def _upstream_url_for_shell(request: Request) -> str:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        return get_upstream_url(session, request.app.state.settings)


def _normalize_render_mode(value: str) -> str:
    return value if value in {"auto", "json", "text", "markdown", "tool", "sse"} else "auto"


def _datetime_iso(value: object) -> str | None:
    text = format_utc_iso(value)
    return text or None


def _datetime_fallback(value: object, variant: str = "full") -> str:
    return format_utc_fallback(value, variant)


def _duration_display(value: object) -> str:
    return format_duration_ms(value)


def _plain_preview(value: object, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return f"{text[: limit - 1]}..."
    return text


def _request_is_error(status: object, error: object) -> bool:
    if error:
        return True
    status_number = _coerce_number(status)
    return status_number is not None and (status_number < 200 or status_number >= 400)


def _request_is_slow(duration_ms: object) -> bool:
    duration = _coerce_number(duration_ms)
    return duration is not None and duration >= SLOW_REQUEST_THRESHOLD_MS


def _request_is_large(total_tokens: object, estimated_input_tokens: object = None) -> bool:
    total = _coerce_number(total_tokens)
    if total is None:
        total = _coerce_number(estimated_input_tokens)
    return total is not None and total >= LARGE_REQUEST_TOKEN_THRESHOLD


def _request_signals(record: dict[str, object]) -> dict[str, bool]:
    return {
        "stream": bool(record["is_stream"]),
        "image": bool(record["has_images"]),
        "tool": bool(record["has_tool_calls"]),
        "error": _request_is_error(record["status"], record["error"]),
        "slow": _request_is_slow(record["duration_ms"]),
        "large": _request_is_large(
            record["tokens"]["total"],
            record.get("estimated_input_tokens"),
        ),
    }


def _semantic_summary(record: dict[str, object]) -> str:
    preview = _plain_preview(record.get("preview"))
    signals = _request_signals(record)
    status = record.get("status")
    if signals["error"]:
        if status and _coerce_number(status) and _coerce_number(status) >= 500:
            prefix = f"Server error {status}"
        elif status:
            prefix = f"HTTP {status}"
        else:
            prefix = "Request error"
        detail = _plain_preview(record.get("error") or preview)
        return f"{prefix} · {detail}" if detail else prefix
    if signals["tool"]:
        summary = "Streaming response" if signals["stream"] else "Response"
        return f"{summary} · Tool call detected"
    if signals["stream"] and (not preview or preview.startswith("data:")):
        return "Streaming response"
    if signals["large"]:
        total_display = format_compact_number(record["tokens"]["total"])
        return f"Long response · {total_display} tokens" + (f" · {preview}" if preview else "")
    return preview


def _stats_json(stats: dict[str, object]) -> dict[str, object]:
    return {
        key: {
            "value": value,
            "display": format_compact_number(value),
        }
        for key, value in stats.items()
    }


def _pagination_json(pagination: dict[str, object]) -> dict[str, object]:
    return {
        "page": pagination["page"],
        "per_page": pagination["per_page"],
        "total": pagination["total"],
        "total_pages": pagination["total_pages"],
        "start": pagination["start"],
        "end": pagination["end"],
        "has_previous": pagination["has_previous"],
        "has_next": pagination["has_next"],
        "previous_url": pagination["previous_url"],
        "next_url": pagination["next_url"],
        "pages": [
            {
                "number": item["number"],
                "url": item["url"],
                "current": item["current"],
            }
            for item in pagination["pages"]
        ],
        "display": {
            "start": format_compact_number(pagination["start"]),
            "end": format_compact_number(pagination["end"]),
            "total": format_compact_number(pagination["total"]),
        },
    }


def _task_run_summary_json(task_run: dict[str, object] | None) -> dict[str, object] | None:
    if task_run is None:
        return None
    run_status = str(task_run["status"])
    return {
        "id": task_run["id"],
        "name": task_run["name"],
        "notes": task_run["notes"],
        "started_at": _datetime_iso(task_run["started_at"]),
        "started_at_fallback": _datetime_fallback(task_run["started_at"]),
        "started_at_table_fallback": _datetime_fallback(task_run["started_at"], "table"),
        "ended_at": _datetime_iso(task_run["ended_at"]),
        "ended_at_fallback": _datetime_fallback(task_run["ended_at"])
        if task_run["ended_at"]
        else None,
        "paused_at": _datetime_iso(task_run["paused_at"]),
        "paused_at_fallback": _datetime_fallback(task_run["paused_at"])
        if task_run["paused_at"]
        else None,
        "is_active": task_run["is_active"],
        "is_paused": task_run["is_paused"],
        "status": run_status,
        "status_label": run_status,
        "open_duration_ms": task_run["open_duration_ms"],
        "open_duration_display": _duration_display(task_run["open_duration_ms"]),
        "request_count": task_run["request_count"],
        "request_count_display": format_compact_number(task_run["request_count"]),
    }


def _task_run_list_item_json(run: dict[str, object]) -> dict[str, object]:
    summary = _task_run_summary_json(run)
    if summary is None:
        return {}
    return {
        **summary,
        "llm_wall_time_ms": run["llm_wall_time_ms"],
        "llm_wall_time_display": _duration_display(run["llm_wall_time_ms"]),
        "total_tokens": run["total_tokens"],
        "total_tokens_display": format_compact_number(run["total_tokens"]),
        "total_cost_usd": _json_safe_number(run["total_cost_usd"]),
        "total_cost_display": format_usd(run["total_cost_usd"]),
        "output_tokens_per_second": run["output_tokens_per_second"],
        "output_tokens_per_second_display": format_compact_rate(
            run["output_tokens_per_second"]
        ),
        "signals": {
            key: {
                "value": value,
                "display": format_compact_number(value),
            }
            for key, value in run["signals"].items()
        },
    }


def _task_run_stats_detail_json(stats: dict[str, object]) -> dict[str, object]:
    return {
        "request_count": stats["request_count"],
        "request_count_display": format_compact_number(stats["request_count"]),
        "success_count": stats["success_count"],
        "success_count_display": format_compact_number(stats["success_count"]),
        "error_count": stats["error_count"],
        "error_count_display": format_compact_number(stats["error_count"]),
        "pending_count": stats["pending_count"],
        "pending_count_display": format_compact_number(stats["pending_count"]),
        "success_rate": _json_safe_number(stats["success_rate"]),
        "success_rate_display": format_percent(stats["success_rate"]),
        "error_rate": _json_safe_number(stats["error_rate"]),
        "error_rate_display": format_percent(stats["error_rate"]),
        "last_activity": _datetime_iso(stats["last_activity"]),
        "last_activity_fallback": _datetime_fallback(stats["last_activity"])
        if stats["last_activity"]
        else None,
        "llm_wall_time_ms": stats["llm_wall_time_ms"],
        "llm_wall_time_display": _duration_display(stats["llm_wall_time_ms"]),
        "run_open_duration_ms": stats["run_open_duration_ms"],
        "run_open_duration_display": _duration_display(stats["run_open_duration_ms"]),
        "total_request_duration_ms": stats["total_request_duration_ms"],
        "total_request_duration_display": _duration_display(
            stats["total_request_duration_ms"]
        ),
        "tokens": {
            key: {"value": value, "display": format_compact_number(value)}
            for key, value in stats["tokens"].items()
        },
        "cost_usd": _json_safe_number(stats["cost_usd"]),
        "cost_display": format_usd(stats["cost_usd"]),
        "throughput": {
            key: {"value": value, "display": format_compact_rate(value)}
            for key, value in stats["throughput"].items()
        },
        "models": _count_rows_json(stats["models"]),
        "endpoints": _count_rows_json(stats["endpoints"]),
        "statuses": _count_rows_json(stats["statuses"]),
        "signals": {
            key: {"value": value, "display": format_compact_number(value)}
            for key, value in stats["signals"].items()
        },
    }


def _count_rows_json(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "label": row["label"],
            "count": row["count"],
            "count_display": format_compact_number(row["count"]),
        }
        for row in rows
    ]


def _record_list_item_json(record: dict[str, object]) -> dict[str, object]:
    status_label = str(record["status"]) if record["status"] is not None else "pending"
    signals = _request_signals(record)
    semantic_summary = record.get("semantic_summary") or _semantic_summary(record)
    return {
        "id": record["id"],
        "created_at": _datetime_iso(record["created_at"]),
        "created_at_fallback": _datetime_fallback(record["created_at"]),
        "created_at_table_fallback": _datetime_fallback(record["created_at"], "table"),
        "method": record["method"],
        "endpoint": record["endpoint"],
        "model": record["model"],
        "upstream_model": record["upstream_model"],
        "model_route": record["model_route"],
        "upstream_url": record.get("upstream_url"),
        "status": record["status"],
        "status_label": status_label,
        "duration_ms": record["duration_ms"],
        "duration_display_ms": record["duration_display_ms"],
        "duration_display": _duration_display(record["duration_display_ms"]),
        "duration_is_elapsed": record["duration_is_elapsed"],
        "is_stream": record["is_stream"],
        "has_images": record["has_images"],
        "has_tool_calls": record["has_tool_calls"],
        "task_run": _task_run_summary_json(record["task_run"]),
        "tokens": _token_triplet_json(record["tokens"]),
        "tokens_per_second": record["tokens_per_second"],
        "tokens_per_second_display": format_compact_rate(record["tokens_per_second"]),
        "cost_usd": _json_safe_number(record["cost_usd"]),
        "cost_display": format_usd(record["cost_usd"]),
        "billing_provider": record["billing_provider"],
        "provider_name": record.get("provider_name") or record["billing_provider"],
        "billing_model": record["billing_model"],
        "route_name": record.get("route_name") or record["model_route"] or "global fallback",
        "response_was_rewritten": record.get("response_was_rewritten", False),
        "compat_fixes_json": record.get("compat_fixes_json"),
        "compat_fix_errors_json": record.get("compat_fix_errors_json"),
        "compatibility_label": _compatibility_label(record),
        "error": record["error"],
        "signals": signals,
        "preview": _plain_preview(record["preview"]),
        "semantic_summary": _plain_preview(semantic_summary),
    }


def _compatibility_label(record: dict[str, object]) -> str:
    if record.get("response_was_rewritten"):
        return "rewritten"
    if record.get("compat_fix_errors_json"):
        return "warned"
    if record.get("compat_fixes_json"):
        return "applied"
    return "none"


def _token_triplet_json(tokens: dict[str, object]) -> dict[str, object]:
    return {
        "input": tokens["input"],
        "input_display": format_compact_number(tokens["input"]),
        "input_estimated": tokens["input_estimated"],
        "cached_input": tokens["cached_input"],
        "cached_input_display": format_compact_number(tokens["cached_input"]),
        "output": tokens["output"],
        "output_display": format_compact_number(tokens["output"]),
        "total": tokens["total"],
        "total_display": format_compact_number(tokens["total"]),
    }


def _record_detail_json(record: dict[str, object]) -> dict[str, object]:
    list_shape = _record_list_item_json(
        {
            **record,
            "status": record["response_status"],
            "tokens": {
                "input": record["display_input_tokens"],
                "input_estimated": False,
                "cached_input": record["display_cached_input_tokens"],
                "output": record["display_output_tokens"],
                "total": record["display_total_tokens"],
            },
            "tokens_per_second": _tokens_per_second(
                record["display_output_tokens"],
                record["duration_ms"],
            ),
            "cost_usd": record["billing_total_cost_usd"],
            "billing_provider": record["billing_provider_name"]
            or record["billing_provider_slug"],
            "preview": "",
        }
    )
    return {
        **list_shape,
        "path": record["path"],
        "query_string": record["query_string"],
        "completed_at": _datetime_iso(record["completed_at"]),
        "completed_at_fallback": _datetime_fallback(record["completed_at"])
        if record["completed_at"]
        else None,
        "upstream_url": record["upstream_url"],
        "request_headers_json": record["request_headers_json"],
        "request_content_type": record["request_content_type"],
        "response_headers_json": record["response_headers_json"],
        "response_content_type": record["response_content_type"],
        "billing_provider_slug": record["billing_provider_slug"],
        "billing_provider_name": record["billing_provider_name"],
        "billing_model": record["billing_model"],
        "billing_input_tokens": record["billing_input_tokens"],
        "billing_cached_input_tokens": record["billing_cached_input_tokens"],
        "billing_output_tokens": record["billing_output_tokens"],
        "billing_total_tokens": record["billing_total_tokens"],
        "billing_input_cost_usd": _json_safe_number(record["billing_input_cost_usd"]),
        "billing_output_cost_usd": _json_safe_number(record["billing_output_cost_usd"]),
        "billing_total_cost_usd": _json_safe_number(record["billing_total_cost_usd"]),
        "billing_total_cost_display": format_usd(record["billing_total_cost_usd"]),
        "pricing_snapshot_json": record["pricing_snapshot_json"],
        "estimated_input_tokens": record["estimated_input_tokens"],
        "estimated_input_tokens_display": format_compact_number(
            record["estimated_input_tokens"]
        ),
        "estimated_input_tokenizer": record["estimated_input_tokenizer"],
        "estimated_input_model": record["estimated_input_model"],
        "response_was_rewritten": record["response_was_rewritten"],
        "compat_fixes_json": record["compat_fixes_json"],
        "compat_fix_errors_json": record["compat_fix_errors_json"],
        "display_input_tokens": record["display_input_tokens"],
        "display_input_tokens_display": format_compact_number(
            record["display_input_tokens"]
        ),
        "display_cached_input_tokens": record["display_cached_input_tokens"],
        "display_cached_input_tokens_display": format_compact_number(
            record["display_cached_input_tokens"]
        ),
        "display_output_tokens": record["display_output_tokens"],
        "display_output_tokens_display": format_compact_number(
            record["display_output_tokens"]
        ),
        "display_total_tokens": record["display_total_tokens"],
        "display_total_tokens_display": format_compact_number(
            record["display_total_tokens"]
        ),
    }


def _rendered_payload_json(rendered) -> dict[str, object] | None:
    if rendered is None:
        return None
    return {
        "mode": rendered.mode,
        "title": rendered.title,
        "text": rendered.text,
        "html": rendered.html,
        "tool_blocks": rendered.tool_blocks or [],
    }


def _count_records(session, stmt) -> int:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return int(session.scalar(count_stmt) or 0)


def _pagination_context(
    request: Request,
    *,
    total: int,
    page: int,
    per_page: int,
) -> dict[str, object]:
    page_size = max(1, min(per_page, 200))
    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(max(page, 1), total_pages)
    offset = (current_page - 1) * page_size
    start = offset + 1 if total else 0
    end = min(total, offset + page_size)
    page_start = max(1, current_page - 2)
    page_end = min(total_pages, current_page + 2)
    return {
        "page": current_page,
        "per_page": page_size,
        "offset": offset,
        "total": total,
        "total_pages": total_pages,
        "start": start,
        "end": end,
        "has_previous": current_page > 1,
        "has_next": current_page < total_pages,
        "previous_url": _page_url(request, current_page - 1, page_size)
        if current_page > 1
        else None,
        "next_url": _page_url(request, current_page + 1, page_size)
        if current_page < total_pages
        else None,
        "pages": [
            {
                "number": page_number,
                "url": _page_url(request, page_number, page_size),
                "current": page_number == current_page,
            }
            for page_number in range(page_start, page_end + 1)
        ],
    }


def _page_url(request: Request, page: int, per_page: int) -> str:
    query_items = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if key not in {"page", "per_page"}
    ]
    query_items.extend((("per_page", str(per_page)), ("page", str(page))))
    return f"{request.url.path}?{urlencode(query_items)}"


def _run_billing_usages(session, run_id: int) -> list[ExtractedTokenUsage]:
    rows = session.execute(
        select(
            RequestRecord.billing_input_tokens,
            RequestRecord.billing_cached_input_tokens,
            RequestRecord.billing_output_tokens,
            RequestRecord.billing_total_tokens,
        ).where(RequestRecord.task_run_id == run_id)
    )
    return [
        ExtractedTokenUsage(
            input_tokens=row[0],
            cached_input_tokens=row[1],
            output_tokens=row[2],
            total_tokens=row[3],
        )
        for row in rows
    ]


async def _settings_with_error(request: Request, error: str) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        total = session.scalar(select(func.count()).select_from(RequestRecord)) or 0
        context = _settings_context(
            request,
            session,
            total=total,
            trim_count=0,
            days=30,
            error=error,
        )
    return templates.TemplateResponse(
        request,
        "settings.html",
        context,
        status_code=400,
    )


async def _runs_with_error(request: Request, error: str) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        runs_with_stats = [
            _task_run_list_item(item["run"], item["stats"], session)
            for item in list_task_runs_with_stats(session)
        ]
        active_run = _task_run_summary(get_active_task_run(session), session)
        upstream_url = get_upstream_url(session, request.app.state.settings)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "runs": runs_with_stats,
            "active_run": active_run,
            "upstream_url": upstream_url,
            "error": error,
            "page_title": "Runs",
        },
        status_code=400,
    )


def _request_error_condition():
    return or_(
        RequestRecord.error.is_not(None),
        RequestRecord.response_status < 200,
        RequestRecord.response_status >= 400,
    )


def _request_provider_options(session) -> list[dict[str, str]]:
    rows = session.execute(
        select(
            RequestRecord.billing_provider_slug,
            RequestRecord.billing_provider_name,
        )
        .where(
            or_(
                RequestRecord.billing_provider_slug.is_not(None),
                RequestRecord.billing_provider_name.is_not(None),
            )
        )
        .distinct()
        .order_by(RequestRecord.billing_provider_name, RequestRecord.billing_provider_slug)
    ).all()
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for slug, name in rows:
        value = slug or name
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({"value": value, "label": name or slug or value})
    return options


def _request_list_items_for_page(
    session,
    stmt,
    pagination: dict[str, object],
) -> list[dict[str, object]]:
    rendered_at = datetime.now(UTC)
    preview = func.substr(RequestRecord.response_body, 1, LIST_RESPONSE_PREVIEW_BYTES)
    response_length = func.length(RequestRecord.response_body)
    rows = session.execute(
        stmt.with_only_columns(
            RequestRecord.id.label("id"),
            RequestRecord.task_run_id.label("task_run_id"),
            RequestRecord.created_at.label("created_at"),
            RequestRecord.completed_at.label("completed_at"),
            RequestRecord.method.label("method"),
            RequestRecord.endpoint.label("endpoint"),
            RequestRecord.model.label("model"),
            RequestRecord.upstream_model.label("upstream_model"),
            RequestRecord.model_route.label("model_route"),
            RequestRecord.upstream_url.label("upstream_url"),
            RequestRecord.response_status.label("response_status"),
            RequestRecord.response_content_type.label("response_content_type"),
            RequestRecord.duration_ms.label("duration_ms"),
            RequestRecord.is_stream.label("is_stream"),
            RequestRecord.has_images.label("has_images"),
            RequestRecord.has_tool_calls.label("has_tool_calls"),
            RequestRecord.billing_provider_slug.label("billing_provider_slug"),
            RequestRecord.billing_provider_name.label("billing_provider_name"),
            RequestRecord.billing_model.label("billing_model"),
            RequestRecord.billing_input_tokens.label("billing_input_tokens"),
            RequestRecord.billing_cached_input_tokens.label("billing_cached_input_tokens"),
            RequestRecord.billing_output_tokens.label("billing_output_tokens"),
            RequestRecord.billing_total_tokens.label("billing_total_tokens"),
            RequestRecord.billing_total_cost_usd.label("billing_total_cost_usd"),
            RequestRecord.estimated_input_tokens.label("estimated_input_tokens"),
            RequestRecord.response_was_rewritten.label("response_was_rewritten"),
            RequestRecord.compat_fixes_json.label("compat_fixes_json"),
            RequestRecord.compat_fix_errors_json.label("compat_fix_errors_json"),
            RequestRecord.error.label("error"),
            preview.label("response_body_preview"),
            response_length.label("response_body_length"),
            TaskRun.id.label("run_id"),
            TaskRun.name.label("run_name"),
            TaskRun.notes.label("run_notes"),
            TaskRun.started_at.label("run_started_at"),
            TaskRun.ended_at.label("run_ended_at"),
            TaskRun.paused_at.label("run_paused_at"),
        )
        .outerjoin(TaskRun, RequestRecord.task_run_id == TaskRun.id)
        .order_by(desc(RequestRecord.created_at))
        .offset(pagination["offset"])
        .limit(pagination["per_page"])
    ).mappings()
    return [_record_list_item_from_row(row, now=rendered_at) for row in rows]


def _record_list_item_from_row(row, *, now: datetime | None = None) -> dict[str, object]:
    response_body = row["response_body_preview"]
    response_length = row["response_body_length"] or 0
    has_complete_preview = response_length <= LIST_RESPONSE_PREVIEW_BYTES
    response_render = render_payload(
        response_body,
        row["response_content_type"],
        "text",
    )
    token_usage = (
        _record_token_usage_from_body(row["is_stream"], response_body)
        if has_complete_preview
        else ExtractedTokenUsage()
    )
    input_tokens = row["billing_input_tokens"]
    if input_tokens is None:
        input_tokens = token_usage.input_tokens
    output_tokens = row["billing_output_tokens"]
    if output_tokens is None:
        output_tokens = token_usage.output_tokens
    total_tokens = row["billing_total_tokens"]
    if total_tokens is None:
        total_tokens = token_usage.total_tokens
    duration = _record_duration_from_values(
        row["created_at"],
        row["completed_at"],
        row["duration_ms"],
        now=now,
    )
    input_is_estimated = (
        input_tokens is None
        and row["completed_at"] is None
        and row["estimated_input_tokens"] is not None
    )
    if input_is_estimated:
        input_tokens = row["estimated_input_tokens"]
    preview = response_render.text
    if preview and not has_complete_preview:
        preview = f"{preview}..."
    item = {
        "id": row["id"],
        "created_at": row["created_at"],
        "method": row["method"],
        "endpoint": row["endpoint"],
        "model": row["model"] or "unknown",
        "upstream_model": row["upstream_model"],
        "model_route": row["model_route"],
        "upstream_url": row["upstream_url"],
        "status": row["response_status"],
        "duration_ms": row["duration_ms"],
        "duration_display_ms": duration["duration_display_ms"],
        "duration_is_elapsed": duration["duration_is_elapsed"],
        "is_stream": row["is_stream"],
        "has_images": row["has_images"],
        "has_tool_calls": row["has_tool_calls"],
        "task_run": _task_run_summary_from_row(row, now=now),
        "tokens": {
            "input": input_tokens,
            "input_estimated": input_is_estimated,
            "cached_input": row["billing_cached_input_tokens"]
            if row["billing_cached_input_tokens"] is not None
            else token_usage.cached_input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        },
        "tokens_per_second": _tokens_per_second(output_tokens, row["duration_ms"]),
        "cost_usd": row["billing_total_cost_usd"],
        "billing_provider": row["billing_provider_name"] or row["billing_provider_slug"],
        "provider_name": row["billing_provider_name"] or row["billing_provider_slug"],
        "billing_model": row["billing_model"],
        "route_name": row["model_route"] or "global fallback",
        "response_was_rewritten": row["response_was_rewritten"],
        "compat_fixes_json": row["compat_fixes_json"],
        "compat_fix_errors_json": row["compat_fix_errors_json"],
        "estimated_input_tokens": row["estimated_input_tokens"],
        "error": row["error"],
        "preview": preview,
    }
    item["signals"] = _request_signals(item)
    item["semantic_summary"] = _semantic_summary(item)
    return item


def _task_run_summary_from_row(row, *, now: datetime | None = None) -> dict[str, object] | None:
    if row["run_id"] is None:
        return None
    ended_at = row["run_ended_at"]
    paused_at = row["run_paused_at"]
    is_active = ended_at is None and paused_at is None
    is_paused = ended_at is None and paused_at is not None
    return {
        "id": row["run_id"],
        "name": row["run_name"],
        "notes": row["run_notes"],
        "started_at": row["run_started_at"],
        "ended_at": ended_at,
        "paused_at": paused_at,
        "is_active": is_active,
        "is_paused": is_paused,
        "status": _run_status(ended_at=ended_at, paused_at=paused_at),
        "open_duration_ms": _duration_ms(
            row["run_started_at"],
            ended_at or now or datetime.now(UTC),
        ),
        "request_count": None,
    }


def _record_list_item(record: RequestRecord, *, now: datetime | None = None) -> dict[str, object]:
    response_render = render_payload(
        record.response_body,
        record.response_content_type,
        "text",
    )
    token_usage = _record_token_usage(record)
    input_tokens = record.billing_input_tokens
    if input_tokens is None:
        input_tokens = token_usage.input_tokens
    output_tokens = record.billing_output_tokens
    if output_tokens is None:
        output_tokens = token_usage.output_tokens
    total_tokens = record.billing_total_tokens
    if total_tokens is None:
        total_tokens = token_usage.total_tokens
    duration = _record_duration(record, now=now)
    input_is_estimated = (
        input_tokens is None
        and record.completed_at is None
        and record.estimated_input_tokens is not None
    )
    if input_is_estimated:
        input_tokens = record.estimated_input_tokens
    item = {
        "id": record.id,
        "created_at": record.created_at,
        "method": record.method,
        "endpoint": record.endpoint,
        "model": record.model or "unknown",
        "upstream_model": record.upstream_model,
        "model_route": record.model_route,
        "upstream_url": record.upstream_url,
        "status": record.response_status,
        "duration_ms": record.duration_ms,
        "duration_display_ms": duration["duration_display_ms"],
        "duration_is_elapsed": duration["duration_is_elapsed"],
        "is_stream": record.is_stream,
        "has_images": record.has_images,
        "has_tool_calls": record.has_tool_calls,
        "task_run": _task_run_summary(record.task_run, session=None),
        "tokens": {
            "input": input_tokens,
            "input_estimated": input_is_estimated,
            "cached_input": record.billing_cached_input_tokens
            if record.billing_cached_input_tokens is not None
            else token_usage.cached_input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        },
        "tokens_per_second": _tokens_per_second(output_tokens, record.duration_ms),
        "cost_usd": record.billing_total_cost_usd,
        "billing_provider": record.billing_provider_name or record.billing_provider_slug,
        "provider_name": record.billing_provider_name or record.billing_provider_slug,
        "billing_model": record.billing_model,
        "route_name": record.model_route or "global fallback",
        "response_was_rewritten": record.response_was_rewritten,
        "compat_fixes_json": record.compat_fixes_json,
        "compat_fix_errors_json": record.compat_fix_errors_json,
        "estimated_input_tokens": record.estimated_input_tokens,
        "error": record.error,
        "preview": response_render.text,
    }
    item["signals"] = _request_signals(item)
    item["semantic_summary"] = _semantic_summary(item)
    return item


def _record_token_usage(record: RequestRecord):
    return _record_token_usage_from_body(record.is_stream, record.response_body)


def _record_token_usage_from_body(
    is_stream: bool,
    response_body: bytes | None,
) -> ExtractedTokenUsage:
    if is_stream:
        return _stream_token_usage(response_body)
    payload = decode_json_bytes(response_body)
    return extract_token_usage(payload)


def _record_effective_token_usage(record: RequestRecord) -> ExtractedTokenUsage:
    token_usage = _record_token_usage(record)
    input_tokens = (
        record.billing_input_tokens
        if record.billing_input_tokens is not None
        else token_usage.input_tokens
    )
    cached_input_tokens = (
        record.billing_cached_input_tokens
        if record.billing_cached_input_tokens is not None
        else token_usage.cached_input_tokens
    )
    output_tokens = (
        record.billing_output_tokens
        if record.billing_output_tokens is not None
        else token_usage.output_tokens
    )
    total_tokens = (
        record.billing_total_tokens
        if record.billing_total_tokens is not None
        else token_usage.total_tokens
    )
    return ExtractedTokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _stream_token_usage(body: bytes | None) -> ExtractedTokenUsage:
    return extract_stream_token_usage(body)


def _record_detail(record: RequestRecord, *, now: datetime | None = None) -> dict[str, object]:
    duration = _record_duration(record, now=now)
    token_usage = _record_effective_token_usage(record)
    return {
        "id": record.id,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
        "method": record.method,
        "path": record.path,
        "query_string": record.query_string,
        "endpoint": record.endpoint,
        "model": record.model,
        "upstream_model": record.upstream_model,
        "model_route": record.model_route,
        "upstream_url": record.upstream_url,
        "request_headers_json": record.request_headers_json,
        "request_body": record.request_body,
        "request_content_type": record.request_content_type,
        "response_status": record.response_status,
        "response_headers_json": record.response_headers_json,
        "response_body": record.response_body,
        "upstream_response_body_raw": record.upstream_response_body_raw,
        "response_content_type": record.response_content_type,
        "duration_ms": record.duration_ms,
        "duration_display_ms": duration["duration_display_ms"],
        "duration_is_elapsed": duration["duration_is_elapsed"],
        "is_stream": record.is_stream,
        "has_images": record.has_images,
        "has_tool_calls": record.has_tool_calls,
        "billing_provider_slug": record.billing_provider_slug,
        "billing_provider_name": record.billing_provider_name,
        "billing_model": record.billing_model,
        "billing_input_tokens": record.billing_input_tokens,
        "billing_cached_input_tokens": record.billing_cached_input_tokens,
        "billing_output_tokens": record.billing_output_tokens,
        "billing_total_tokens": record.billing_total_tokens,
        "display_input_tokens": token_usage.input_tokens,
        "display_cached_input_tokens": token_usage.cached_input_tokens,
        "display_output_tokens": token_usage.output_tokens,
        "display_total_tokens": token_usage.total_tokens,
        "billing_input_cost_usd": record.billing_input_cost_usd,
        "billing_output_cost_usd": record.billing_output_cost_usd,
        "billing_total_cost_usd": record.billing_total_cost_usd,
        "pricing_snapshot_json": record.pricing_snapshot_json,
        "estimated_input_tokens": record.estimated_input_tokens,
        "estimated_input_tokenizer": record.estimated_input_tokenizer,
        "estimated_input_model": record.estimated_input_model,
        "response_was_rewritten": record.response_was_rewritten,
        "compat_fixes_json": record.compat_fixes_json,
        "compat_fix_errors_json": record.compat_fix_errors_json,
        "task_run": _task_run_summary(record.task_run, session=None),
        "error": record.error,
    }


def _record_duration(record: RequestRecord, *, now: datetime | None) -> dict[str, object]:
    return _record_duration_from_values(
        record.created_at,
        record.completed_at,
        record.duration_ms,
        now=now,
    )


def _record_duration_from_values(
    created_at: datetime,
    completed_at: datetime | None,
    duration_ms: int | None,
    *,
    now: datetime | None,
) -> dict[str, object]:
    if duration_ms is not None:
        return {"duration_display_ms": duration_ms, "duration_is_elapsed": False}
    if completed_at is None:
        elapsed_ms = _duration_ms(created_at, now or datetime.now(UTC))
        return {"duration_display_ms": elapsed_ms, "duration_is_elapsed": elapsed_ms is not None}
    return {"duration_display_ms": None, "duration_is_elapsed": False}


def _task_run_summary(task_run: TaskRun | None, session=None) -> dict[str, object] | None:
    if task_run is None:
        return None
    ended_at = task_run.ended_at
    paused_at = task_run.paused_at
    is_active = ended_at is None and paused_at is None
    is_paused = ended_at is None and paused_at is not None
    now = datetime.now(UTC)
    request_count = None
    if session is not None:
        request_count = (
            session.scalar(
                select(func.count()).where(RequestRecord.task_run_id == task_run.id)
            )
            or 0
        )
    return {
        "id": task_run.id,
        "name": task_run.name,
        "notes": task_run.notes,
        "started_at": task_run.started_at,
        "ended_at": ended_at,
        "paused_at": paused_at,
        "is_active": is_active,
        "is_paused": is_paused,
        "status": _run_status(ended_at=ended_at, paused_at=paused_at),
        "open_duration_ms": _duration_ms(task_run.started_at, ended_at or now),
        "request_count": request_count,
    }


def _run_status(*, ended_at: datetime | None, paused_at: datetime | None) -> str:
    if ended_at is not None:
        return "complete"
    if paused_at is not None:
        return "paused"
    return "active"


def _task_run_list_item(
    task_run: TaskRun,
    stats: dict[str, object],
    session,
) -> dict[str, object]:
    detail = _task_run_stats_detail(task_run, session)
    summary = _task_run_summary(task_run, session=None)
    return {
        **(summary or {}),
        "request_count": stats["request_count"],
        "llm_wall_time_ms": stats["llm_wall_time_ms"],
        "total_tokens": detail["tokens"]["total"],
        "total_cost_usd": detail["cost_usd"],
        "output_tokens_per_second": detail["throughput"]["output_observed"],
        "signals": detail["signals"],
    }


def _task_run_stats_detail(task_run: TaskRun, session) -> dict[str, object]:
    base_stats = get_task_run_stats(session, task_run.id)
    run_open_duration_ms = _duration_ms(
        task_run.started_at,
        task_run.ended_at or datetime.now(UTC),
    )
    token_row = session.execute(
        select(
            func.sum(RequestRecord.billing_input_tokens),
            func.sum(RequestRecord.billing_output_tokens),
            func.sum(RequestRecord.billing_total_tokens),
            func.sum(RequestRecord.billing_total_cost_usd),
        ).where(RequestRecord.task_run_id == task_run.id)
    ).one()
    health_row = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            (RequestRecord.response_status >= 200)
                            & (RequestRecord.response_status < 400),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(case((_request_error_condition(), 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((RequestRecord.response_status.is_(None), 1), else_=0)),
                0,
            ),
            func.max(RequestRecord.created_at),
        ).where(RequestRecord.task_run_id == task_run.id)
    ).one()

    token_totals = {
        "input": _coerce_int_or_none(token_row[0]),
        "output": _coerce_int_or_none(token_row[1]),
        "total": _coerce_int_or_none(token_row[2]),
    }
    llm_wall_time_ms = base_stats["llm_wall_time_ms"]
    total_request_duration_ms = base_stats["total_request_duration_ms"]
    request_count = int(base_stats["request_count"] or 0)
    success_count = int(health_row[0] or 0)
    error_count = int(health_row[1] or 0)
    return {
        **base_stats,
        "run_open_duration_ms": run_open_duration_ms,
        "success_count": success_count,
        "error_count": error_count,
        "pending_count": int(health_row[2] or 0),
        "success_rate": success_count / request_count if request_count else None,
        "error_rate": error_count / request_count if request_count else None,
        "last_activity": health_row[3],
        "tokens": token_totals,
        "cost_usd": token_row[3],
        "throughput": {
            "output_wall": _tokens_per_second(token_totals["output"], llm_wall_time_ms),
            "total_wall": _tokens_per_second(token_totals["total"], llm_wall_time_ms),
            "output_observed": _tokens_per_second(
                token_totals["output"],
                total_request_duration_ms,
            ),
        },
        "models": _grouped_count_rows(
            session,
            RequestRecord.model,
            task_run.id,
            none_label="unknown",
        ),
        "endpoints": _grouped_count_rows(session, RequestRecord.endpoint, task_run.id),
        "statuses": _grouped_count_rows(
            session,
            RequestRecord.response_status,
            task_run.id,
            none_label="pending",
        ),
        "signals": {
            "streams": base_stats["streams"],
            "images": base_stats["images"],
            "tools": base_stats["tools"],
            "errors": error_count,
        },
    }


def _coerce_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _grouped_count_rows(
    session,
    column,
    task_run_id: int,
    *,
    none_label: str | None = None,
) -> list[dict[str, object]]:
    rows = session.execute(
        select(column, func.count())
        .where(RequestRecord.task_run_id == task_run_id)
        .group_by(column)
        .order_by(desc(func.count()))
    )
    return [
        {
            "label": str(value) if value is not None else (none_label or "-"),
            "count": count,
        }
        for value, count in rows
    ]


def _sum_known(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known)


def _sum_decimal_known(values: list[Decimal | None]) -> Decimal | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known, Decimal("0"))


def _tokens_per_second(tokens: int | None, duration_ms: object) -> str | None:
    if tokens is None or not isinstance(duration_ms, int) or duration_ms <= 0:
        return None
    return f"{tokens / (duration_ms / 1000):.2f}"


def _counter_rows(values) -> list[dict[str, object]]:
    return [
        {"label": label, "count": count}
        for label, count in Counter(values).most_common()
    ]


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None and ended_at.tzinfo is not None:
        ended_at = ended_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and ended_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((ended_at - started_at).total_seconds() * 1000))
