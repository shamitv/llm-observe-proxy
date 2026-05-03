from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Undefined, pass_context
from sqlalchemy import desc, func, select
from starlette.templating import Jinja2Templates

from llm_observe_proxy.capture import (
    ExtractedTokenUsage,
    decode_json_bytes,
    decode_sse_json_events,
    extract_token_usage,
)
from llm_observe_proxy.config import ModelRoute, normalize_upstream_url
from llm_observe_proxy.database import (
    RequestRecord,
    SessionFactory,
    TaskRun,
    delete_ui_model_route,
    end_active_task_run,
    get_active_task_run,
    get_effective_model_routes,
    get_expose_all_ips,
    get_incoming_host,
    get_incoming_port,
    get_task_run_stats,
    get_ui_model_routes,
    get_upstream_url,
    list_task_runs_with_stats,
    session_scope,
    set_incoming_server,
    set_setting,
    start_task_run,
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


def _coerce_number(value: object) -> float | None:
    if value is None or isinstance(value, Undefined) or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
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

router = APIRouter(prefix="/admin", include_in_schema=False)

TEST_PROMPT_DEFAULT = "Reply with a short upstream connectivity check."
TEST_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
STREAM_USAGE_MARKERS = (
    b'"usage"',
    b'"input_tokens"',
    b'"prompt_tokens"',
    b'"output_tokens"',
    b'"completion_tokens"',
    b'"total_tokens"',
)


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
    limit: int = Query(100, ge=1, le=500),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        stmt = select(RequestRecord).order_by(desc(RequestRecord.created_at)).limit(limit)
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

        records = [_record_list_item(record) for record in session.scalars(stmt).all()]
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
                "limit": limit,
            },
            "run_options": [_task_run_summary(task_run, session=None) for task_run in run_options],
            "active_run": active_run,
            "stats": stats,
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
        detail_record = _record_detail(record)
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
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "record": detail_record,
            "images": images,
            "request_render": request_render,
            "response_render": response_render,
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
async def run_detail(request: Request, run_id: int) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        task_run = session.get(TaskRun, run_id)
        if task_run is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"record_id": run_id, "page_title": "Run Not Found"},
                status_code=404,
            )
        records = [
            _record_list_item(record)
            for record in session.scalars(
                select(RequestRecord)
                .where(RequestRecord.task_run_id == run_id)
                .order_by(desc(RequestRecord.created_at))
            ).all()
        ]
        stats = _task_run_stats_detail(task_run, session)
        active_run = _task_run_summary(get_active_task_run(session), session)
        upstream_url = get_upstream_url(session, request.app.state.settings)

    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": _task_run_summary(task_run, session=None),
            "records": records,
            "stats": stats,
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


@router.post("/settings/model-routes", response_class=HTMLResponse)
async def upsert_model_route(
    request: Request,
    model: str = Form(...),
    upstream_url: str = Form(...),
    upstream_model: str = Form(""),
    api_key_env: str = Form(""),
) -> HTMLResponse:
    settings = request.app.state.settings
    try:
        route = ModelRoute(
            model=model,
            upstream_url=upstream_url,
            upstream_model=upstream_model,
            api_key_env=api_key_env,
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
    return {
        "upstream_url": get_upstream_url(session, settings),
        "model_routes": _settings_model_route_rows(session, settings),
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


def _settings_model_route_rows(session, settings) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for route in settings.model_routes:
        row = model_route_display(route)
        row["source"] = "startup"
        row["editable"] = False
        rows.append(row)
    for route in get_ui_model_routes(session):
        row = model_route_display(route)
        row["source"] = "ui"
        row["editable"] = True
        rows.append(row)
    return rows


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


def _record_list_item(record: RequestRecord) -> dict[str, object]:
    response_render = render_payload(
        record.response_body,
        record.response_content_type,
        "text",
    )
    token_usage = _record_token_usage(record)
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
        "is_stream": record.is_stream,
        "has_images": record.has_images,
        "has_tool_calls": record.has_tool_calls,
        "task_run": _task_run_summary(record.task_run, session=None),
        "tokens": {
            "input": token_usage.input_tokens,
            "output": token_usage.output_tokens,
            "total": token_usage.total_tokens,
        },
        "tokens_per_second": _tokens_per_second(token_usage.output_tokens, record.duration_ms),
        "error": record.error,
        "preview": response_render.text,
    }


def _record_token_usage(record: RequestRecord):
    if record.is_stream:
        return _stream_token_usage(record.response_body)
    else:
        payload = decode_json_bytes(record.response_body)
    return extract_token_usage(payload)


def _stream_token_usage(body: bytes | None) -> ExtractedTokenUsage:
    if not body or not _body_may_contain_usage(body):
        return ExtractedTokenUsage()

    usage_index = max(body.rfind(marker) for marker in STREAM_USAGE_MARKERS)
    data_index = body.rfind(b"data:", 0, usage_index)
    if data_index >= 0:
        event_end = body.find(b"\n\n", usage_index)
        if event_end < 0:
            event_end = len(body)
        event = body[data_index:event_end]
        try:
            text = event.decode("utf-8")
            data = "\n".join(
                line.removeprefix("data:").strip()
                for line in text.splitlines()
                if line.startswith("data:")
            )
            if data and data != "[DONE]":
                return extract_token_usage(json.loads(data))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    return extract_token_usage(decode_sse_json_events(body))


def _body_may_contain_usage(body: bytes | None) -> bool:
    if not body:
        return False
    return any(marker in body for marker in STREAM_USAGE_MARKERS)


def _record_detail(record: RequestRecord) -> dict[str, object]:
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
        "response_content_type": record.response_content_type,
        "duration_ms": record.duration_ms,
        "is_stream": record.is_stream,
        "has_images": record.has_images,
        "has_tool_calls": record.has_tool_calls,
        "task_run": _task_run_summary(record.task_run, session=None),
        "error": record.error,
    }


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
        "output_tokens_per_second": detail["throughput"]["output_wall"],
        "signals": detail["signals"],
    }


def _task_run_stats_detail(task_run: TaskRun, session) -> dict[str, object]:
    records = session.scalars(
        select(RequestRecord)
        .where(RequestRecord.task_run_id == task_run.id)
        .order_by(RequestRecord.created_at)
    ).all()
    base_stats = get_task_run_stats(session, task_run.id)
    run_open_duration_ms = _duration_ms(
        task_run.started_at,
        task_run.ended_at or datetime.now(UTC),
    )
    input_tokens: list[int | None] = []
    output_tokens: list[int | None] = []
    total_tokens: list[int | None] = []
    for record in records:
        token_usage = _record_token_usage(record)
        input_tokens.append(token_usage.input_tokens)
        output_tokens.append(token_usage.output_tokens)
        total_tokens.append(token_usage.total_tokens)

    token_totals = {
        "input": _sum_known(input_tokens),
        "output": _sum_known(output_tokens),
        "total": _sum_known(total_tokens),
    }
    llm_wall_time_ms = base_stats["llm_wall_time_ms"]
    total_request_duration_ms = base_stats["total_request_duration_ms"]
    return {
        **base_stats,
        "run_open_duration_ms": run_open_duration_ms,
        "tokens": token_totals,
        "throughput": {
            "output_wall": _tokens_per_second(token_totals["output"], llm_wall_time_ms),
            "total_wall": _tokens_per_second(token_totals["total"], llm_wall_time_ms),
            "output_observed": _tokens_per_second(
                token_totals["output"],
                total_request_duration_ms,
            ),
        },
        "models": _counter_rows(record.model or "unknown" for record in records),
        "endpoints": _counter_rows(record.endpoint for record in records),
        "statuses": _counter_rows(
            str(record.response_status) if record.response_status is not None else "pending"
            for record in records
        ),
        "signals": {
            "streams": base_stats["streams"],
            "images": base_stats["images"],
            "tools": base_stats["tools"],
            "errors": base_stats["errors"],
        },
    }


def _sum_known(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known)


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
