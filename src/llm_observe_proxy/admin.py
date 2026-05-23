from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Undefined, pass_context
from sqlalchemy import desc, func, select
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
from llm_observe_proxy.config import ModelRoute, normalize_upstream_url
from llm_observe_proxy.costing import RunCostEstimate, estimate_run_cost
from llm_observe_proxy.database import (
    ModelPrice,
    RequestRecord,
    SessionFactory,
    TaskRun,
    delete_model_price,
    delete_model_price_tier,
    delete_model_provider,
    delete_ui_model_route,
    end_active_task_run,
    get_active_task_run,
    get_default_compat_fixes,
    get_effective_model_routes,
    get_expose_all_ips,
    get_incoming_host,
    get_incoming_port,
    get_task_run_stats,
    get_ui_model_routes,
    get_upstream_url,
    list_model_prices,
    list_model_providers,
    list_task_runs_with_stats,
    session_scope,
    set_default_compat_fixes,
    set_incoming_server,
    set_setting,
    start_task_run,
    upsert_model_price,
    upsert_model_price_tier,
    upsert_model_provider,
    upsert_ui_model_route,
)
from llm_observe_proxy.rendering import escape_preview, render_payload
from llm_observe_proxy.routing import (
    build_forward_body,
    build_forward_headers,
    model_route_display,
    select_model_route,
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

TEST_PROMPT_DEFAULT = "Reply with a short upstream connectivity check."
TEST_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
DEFAULT_RUN_WHAT_IF_KEYS = ("openai:gpt-5.5", "openai:gpt-5.4-mini")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    endpoint: str | None = None,
    model: str | None = None,
    status: int | None = None,
    run: int | None = None,
    stream: str | None = None,
    image: str | None = None,
    tool: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        stmt = select(RequestRecord)
        if endpoint:
            stmt = stmt.where(RequestRecord.endpoint.like(f"%{endpoint}%"))
        if model:
            stmt = stmt.where(RequestRecord.model == model)
        if status is not None:
            stmt = stmt.where(RequestRecord.response_status == status)
        if run is not None:
            stmt = stmt.where(RequestRecord.task_run_id == run)
        if stream == "1":
            stmt = stmt.where(RequestRecord.is_stream.is_(True))
        if image == "1":
            stmt = stmt.where(RequestRecord.has_images.is_(True))
        if tool == "1":
            stmt = stmt.where(RequestRecord.has_tool_calls.is_(True))

        total_records = _count_records(session, stmt)
        pagination = _pagination_context(
            request,
            total=total_records,
            page=page,
            per_page=per_page,
        )
        rendered_at = datetime.now(UTC)
        records = [
            _record_list_item(record, now=rendered_at)
            for record in session.scalars(
                stmt.order_by(desc(RequestRecord.created_at))
                .offset(pagination["offset"])
                .limit(pagination["per_page"])
            ).all()
        ]
        models = [
            row[0]
            for row in session.execute(
                select(RequestRecord.model).where(RequestRecord.model.is_not(None)).distinct()
            )
        ]
        endpoints = [row[0] for row in session.execute(select(RequestRecord.endpoint).distinct())]
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
        }
        upstream_url = get_upstream_url(session, request.app.state.settings)
        active_run = _task_run_summary(get_active_task_run(session), session)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "records": records,
            "models": models,
            "endpoints": endpoints,
            "filters": {
                "endpoint": endpoint or "",
                "model": model or "",
                "status": status or "",
                "run": run or "",
                "stream": stream == "1",
                "image": image == "1",
                "tool": tool == "1",
                "page": pagination["page"],
                "per_page": pagination["per_page"],
            },
            "run_options": [_task_run_summary(task_run, session=None) for task_run in run_options],
            "active_run": active_run,
            "stats": stats,
            "pagination": pagination,
            "upstream_url": upstream_url,
            "page_title": "Request Browser",
        },
    )


@router.get("/requests/{record_id}", response_class=HTMLResponse)
async def detail(request: Request, record_id: int, mode: str = "auto") -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        record = session.get(RequestRecord, record_id)
        if record is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"record_id": record_id, "page_title": "Not Found"},
                status_code=404,
            )
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

    request_render = render_payload(
        detail_record["request_body"],
        detail_record["request_content_type"],
        "json",
    )
    response_render = render_payload(
        detail_record["response_body"],
        detail_record["response_content_type"],
        mode,
    )
    raw_response_render = (
        render_payload(
            detail_record["upstream_response_body_raw"],
            detail_record["response_content_type"],
            mode,
        )
        if detail_record["upstream_response_body_raw"]
        else None
    )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "record": detail_record,
            "images": images,
            "request_render": request_render,
            "response_render": response_render,
            "raw_response_render": raw_response_render,
            "mode": response_render.mode if mode == "auto" else mode,
            "active_run": active_run,
            "upstream_url": upstream_url,
            "page_title": f"Request #{record_id}",
        },
    )


@router.get("/runs", response_class=HTMLResponse)
async def runs(request: Request) -> HTMLResponse:
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
            "page_title": "Runs",
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request,
    run_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    what_if = request.query_params.getlist("what_if") or None
    with session_scope(session_factory) as session:
        task_run = session.get(TaskRun, run_id)
        if task_run is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"record_id": run_id, "page_title": "Run Not Found"},
                status_code=404,
            )
        request_stmt = select(RequestRecord).where(RequestRecord.task_run_id == run_id)
        total_records = _count_records(session, request_stmt)
        pagination = _pagination_context(
            request,
            total=total_records,
            page=page,
            per_page=per_page,
        )
        request_records = session.scalars(
            request_stmt.order_by(desc(RequestRecord.created_at))
            .offset(pagination["offset"])
            .limit(pagination["per_page"])
        ).all()
        rendered_at = datetime.now(UTC)
        records = [_record_list_item(record, now=rendered_at) for record in request_records]
        stats = _task_run_stats_detail(task_run, session)
        what_if_costs = _run_what_if_context(
            _run_billing_usages(session, run_id),
            session,
            requested_keys=what_if,
        )
        active_run = _task_run_summary(get_active_task_run(session), session)
        upstream_url = get_upstream_url(session, request.app.state.settings)

    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": _task_run_summary(task_run, session=None),
            "records": records,
            "stats": stats,
            "what_if": what_if_costs,
            "pagination": pagination,
            "active_run": active_run,
            "upstream_url": upstream_url,
            "page_title": f"Run: {task_run.name}",
        },
    )


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


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, days: int = Query(30, ge=1, le=3650)) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope(session_factory) as session:
        total = session.scalar(select(func.count()).select_from(RequestRecord)) or 0
        trim_count = session.scalar(
            select(func.count()).where(RequestRecord.created_at < cutoff)
        ) or 0
        context = _settings_context(request, session, total=total, trim_count=trim_count, days=days)

    return templates.TemplateResponse(
        request,
        "settings.html",
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
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/upstream", response_class=HTMLResponse)
async def update_upstream(request: Request, upstream_url: str = Form(...)) -> HTMLResponse:
    try:
        normalized = normalize_upstream_url(upstream_url)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        set_setting(session, "upstream_url", normalized)
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/compat-fixes", response_class=HTMLResponse)
async def update_default_compat_fixes(request: Request, fixes: str = Form("")) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        parsed_fixes = normalize_fix_ids(fixes)
        with session_scope(session_factory) as session:
            set_default_compat_fixes(session, parsed_fixes)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/model-routes", response_class=HTMLResponse)
async def upsert_model_route(
    request: Request,
    model: str = Form(...),
    upstream_url: str = Form(...),
    upstream_model: str = Form(""),
    provider_slug: str = Form(""),
    api_key_env: str = Form(""),
    fixes: str = Form(""),
) -> HTMLResponse:
    settings = request.app.state.settings
    try:
        route = ModelRoute(
            model=model,
            upstream_url=upstream_url,
            upstream_model=upstream_model,
            provider_slug=provider_slug,
            api_key_env=api_key_env,
            fixes=normalize_fix_ids(fixes),
        )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        try:
            upsert_ui_model_route(session, settings, route)
        except ValueError as exc:
            return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/model-routes/delete", response_class=HTMLResponse)
async def delete_model_route(request: Request, model: str = Form(...)) -> HTMLResponse:
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
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/providers", response_class=HTMLResponse)
async def upsert_provider(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    upstream_url: str = Form(""),
    currency: str = Form("USD"),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            upsert_model_provider(
                session,
                slug=slug,
                name=name,
                upstream_url=upstream_url,
                currency=currency,
            )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/providers/delete", response_class=HTMLResponse)
async def delete_provider(request: Request, slug: str = Form(...)) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    try:
        with session_scope(session_factory) as session:
            if not delete_model_provider(session, slug):
                return await _settings_with_error(request, "Provider was not found.")
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings", status_code=303)


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
                active=active == "yes",
                notes=notes,
            )
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))
    return RedirectResponse("/admin/settings", status_code=303)


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
    return RedirectResponse("/admin/settings", status_code=303)


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
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/model-price-tiers/delete", response_class=HTMLResponse)
async def delete_price_tier(
    request: Request,
    tier_id: int = Form(...),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        if not delete_model_price_tier(session, tier_id):
            return await _settings_with_error(request, "Model price tier was not found.")
    return RedirectResponse("/admin/settings", status_code=303)


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

    days = 30
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
            test_result=result,
            test_model=model.strip() or "gpt-test",
            test_prompt=prompt.strip() or TEST_PROMPT_DEFAULT,
        )

    return templates.TemplateResponse(request, "settings.html", context)


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
    return RedirectResponse(f"/admin/settings?days={days}&trimmed={deleted}", status_code=303)


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
    return {
        "upstream_url": get_upstream_url(session, settings),
        "model_routes": _settings_model_route_rows(session, settings, providers),
        "default_compat_fixes": default_fixes,
        "default_compat_fixes_text": fix_ids_text(default_fixes),
        "available_compat_fixes": compatibility_fix_rows(),
        "providers": [_provider_row(provider) for provider in providers],
        "model_prices": [_model_price_row(price) for price in list_model_prices(session)],
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
    for route in get_ui_model_routes(session):
        row = model_route_display(route)
        row["source"] = "ui"
        row["editable"] = True
        row["provider_name"] = provider_names.get(route.provider_slug or "")
        row["fixes_text"] = fix_ids_text(route.fixes)
        rows.append(row)
    return rows


def _provider_row(provider) -> dict[str, object]:
    return {
        "slug": provider.slug,
        "name": provider.name,
        "upstream_url": provider.upstream_url,
        "currency": provider.currency,
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
        "scenarios": scenarios,
        "message": message,
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
    return {
        "key": key,
        "provider_name": price.provider.name,
        "model": price.model,
        "display_name": price.display_name,
        "label": price.display_name or price.model,
        "checked": checked,
    }


def _run_cost_estimate_row(estimate: RunCostEstimate) -> dict[str, object]:
    return {
        "key": f"{estimate.provider_slug}:{estimate.model}",
        "provider_name": estimate.provider_name,
        "model": estimate.model,
        "display_name": estimate.display_name,
        "label": estimate.display_name or estimate.model,
        "input_usd_per_million": estimate.input_usd_per_million,
        "cached_input_usd_per_million": estimate.cached_input_usd_per_million,
        "output_usd_per_million": estimate.output_usd_per_million,
        "mixed_tiers": estimate.mixed_tiers,
        "input_tokens": estimate.input_tokens,
        "cached_input_tokens": estimate.cached_input_tokens,
        "cache_write_input_tokens": estimate.cache_write_input_tokens,
        "output_tokens": estimate.output_tokens,
        "total_tokens": estimate.total_tokens,
        "input_cost_usd": estimate.input_cost_usd,
        "cached_input_cost_usd": estimate.cached_input_cost_usd,
        "output_cost_usd": estimate.output_cost_usd,
        "total_cost_usd": estimate.total_cost_usd,
        "included_request_count": estimate.included_request_count,
        "missing_usage_request_count": estimate.missing_usage_request_count,
        "notes": estimate.notes,
    }


def _model_price_key(price: ModelPrice) -> str:
    return f"{price.provider_slug}:{price.model}"


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
    return {
        "id": record.id,
        "created_at": record.created_at,
        "method": record.method,
        "endpoint": record.endpoint,
        "model": record.model or "unknown",
        "upstream_model": record.upstream_model,
        "model_route": record.model_route,
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
        "billing_model": record.billing_model,
        "error": record.error,
        "preview": response_render.text,
    }


def _record_token_usage(record: RequestRecord):
    if record.is_stream:
        return _stream_token_usage(record.response_body)
    else:
        payload = decode_json_bytes(record.response_body)
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
    if record.duration_ms is not None:
        return {"duration_display_ms": record.duration_ms, "duration_is_elapsed": False}
    if record.completed_at is None:
        elapsed_ms = _duration_ms(record.created_at, now or datetime.now(UTC))
        return {"duration_display_ms": elapsed_ms, "duration_is_elapsed": elapsed_ms is not None}
    return {"duration_display_ms": None, "duration_is_elapsed": False}


def _task_run_summary(task_run: TaskRun | None, session=None) -> dict[str, object] | None:
    if task_run is None:
        return None
    ended_at = task_run.ended_at
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
        "is_active": ended_at is None,
        "open_duration_ms": _duration_ms(task_run.started_at, ended_at or now),
        "request_count": request_count,
    }


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

    token_totals = {
        "input": _coerce_int_or_none(token_row[0]),
        "output": _coerce_int_or_none(token_row[1]),
        "total": _coerce_int_or_none(token_row[2]),
    }
    llm_wall_time_ms = base_stats["llm_wall_time_ms"]
    total_request_duration_ms = base_stats["total_request_duration_ms"]
    return {
        **base_stats,
        "run_open_duration_ms": run_open_duration_ms,
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
            "errors": base_stats["errors"],
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
