from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import pass_context
from sqlalchemy import desc, func, select
from starlette.templating import Jinja2Templates

from llm_observe_proxy.database import (
    RequestRecord,
    SessionFactory,
    get_expose_all_ips,
    get_incoming_host,
    get_incoming_port,
    get_upstream_url,
    session_scope,
    set_incoming_server,
    set_setting,
)
from llm_observe_proxy.rendering import escape_preview, render_payload

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.filters["preview"] = escape_preview


@pass_context
def is_active_mode(context, mode: str) -> str:
    return "active" if context.get("mode") == mode else ""


templates.env.filters["active_mode"] = is_active_mode

router = APIRouter(prefix="/admin", include_in_schema=False)

TEST_PROMPT_DEFAULT = "Reply with a short upstream connectivity check."
TEST_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    endpoint: str | None = None,
    model: str | None = None,
    status: int | None = None,
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
                "stream": stream == "1",
                "image": image == "1",
                "tool": tool == "1",
                "limit": limit,
            },
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
            "page_title": f"Request #{record_id}",
        },
    )


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


@router.post("/settings/test-upstream", response_class=HTMLResponse)
async def test_upstream(
    request: Request,
    test_kind: str = Form(...),
    model: str = Form("gpt-test"),
    prompt: str = Form(TEST_PROMPT_DEFAULT),
) -> HTMLResponse:
    session_factory: SessionFactory = request.app.state.session_factory
    with session_scope(session_factory) as session:
        upstream_url = get_upstream_url(session, request.app.state.settings)

    try:
        payload = build_upstream_test_payload(test_kind, model, prompt)
    except ValueError as exc:
        return await _settings_with_error(request, str(exc))

    chat_url = f"{upstream_url.rstrip('/')}/chat/completions"
    result = await _send_upstream_test(chat_url, payload, test_kind)

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


def normalize_upstream_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Upstream URL must be an absolute http(s) URL.")
    if not normalized.endswith("/v1"):
        raise ValueError("Upstream URL must point to a /v1 base URL.")
    return normalized


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
    payload: dict[str, Any],
    test_kind: str,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(chat_url, json=payload)
    except httpx.HTTPError as exc:
        return {
            "kind": test_kind,
            "url": chat_url,
            "ok": False,
            "error": str(exc),
            "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
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
    return {
        "upstream_url": get_upstream_url(session, request.app.state.settings),
        "incoming_host": get_incoming_host(session, request.app.state.settings),
        "incoming_port": get_incoming_port(session, request.app.state.settings),
        "expose_all_ips": get_expose_all_ips(session, request.app.state.settings),
        "days": days,
        "total": total,
        "trim_count": trim_count,
        "error": error,
        "test_result": test_result,
        "test_model": test_model,
        "test_prompt": test_prompt,
        "page_title": "Settings",
    }


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


def _record_list_item(record: RequestRecord) -> dict[str, object]:
    response_render = render_payload(
        record.response_body,
        record.response_content_type,
        "text",
    )
    return {
        "id": record.id,
        "created_at": record.created_at,
        "method": record.method,
        "endpoint": record.endpoint,
        "model": record.model or "unknown",
        "status": record.response_status,
        "duration_ms": record.duration_ms,
        "is_stream": record.is_stream,
        "has_images": record.has_images,
        "has_tool_calls": record.has_tool_calls,
        "error": record.error,
        "preview": response_render.text,
    }


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
        "error": record.error,
    }
