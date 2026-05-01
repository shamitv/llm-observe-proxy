from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from llm_observe_proxy.capture import (
    compact_json,
    decode_json_bytes,
    extract_images,
    extract_model,
    has_tool_payload,
)
from llm_observe_proxy.database import (
    ImageAsset,
    RequestRecord,
    SessionFactory,
    get_upstream_url,
    session_scope,
)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
RESPONSE_DROP_HEADERS = HOP_BY_HOP_HEADERS | {"content-encoding"}


router = APIRouter()


@router.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_openai(path: str, request: Request) -> Response:
    settings = request.app.state.settings
    session_factory: SessionFactory = request.app.state.session_factory
    request_body = await request.body()
    request_payload = decode_json_bytes(request_body)
    request_headers = _headers_to_dict(request.headers)
    query_string = request.url.query

    with _session(session_factory) as session:
        upstream_base = get_upstream_url(session, settings)
        upstream_url = _build_upstream_url(upstream_base, path, query_string)
        images = extract_images(request_payload)
        record = RequestRecord(
            method=request.method,
            path=f"/v1/{path}",
            query_string=query_string,
            endpoint=f"/v1/{path}",
            model=extract_model(request_payload),
            upstream_url=upstream_url,
            request_headers_json=compact_json(request_headers),
            request_body=request_body,
            request_content_type=request.headers.get("content-type"),
            is_stream=_is_stream_request(request_payload, request.headers),
            has_images=bool(images),
            has_tool_calls=has_tool_payload(request_payload),
        )
        record.images = [
            ImageAsset(
                kind=image.kind,
                mime_type=image.mime_type,
                source=image.source,
                data_base64=image.data_base64,
            )
            for image in images
        ]
        session.add(record)
        session.commit()
        session.refresh(record)
        record_id = record.id

    started = time.perf_counter()
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        upstream_response = await client.request(
            request.method,
            upstream_url,
            content=request_body,
            headers=_forward_headers(request.headers),
        )
        response_body = upstream_response.content
        response_headers = _headers_to_dict(upstream_response.headers)
        response_payload = decode_json_bytes(response_body)
        duration_ms = int((time.perf_counter() - started) * 1000)

        with _session(session_factory) as session:
            record = session.get(RequestRecord, record_id)
            if record is not None:
                record.completed_at = _now_from_record(record)
                record.response_status = upstream_response.status_code
                record.response_headers_json = compact_json(response_headers)
                record.response_body = response_body
                record.response_content_type = upstream_response.headers.get("content-type")
                record.duration_ms = duration_ms
                record.has_tool_calls = record.has_tool_calls or has_tool_payload(response_payload)

        return Response(
            content=response_body,
            status_code=upstream_response.status_code,
            headers=_response_headers(upstream_response.headers),
        )
    except httpx.HTTPError as exc:
        error_body = {"error": {"message": str(exc), "type": "upstream_error"}}
        encoded_error = json.dumps(error_body).encode("utf-8")
        duration_ms = int((time.perf_counter() - started) * 1000)
        with _session(session_factory) as session:
            record = session.get(RequestRecord, record_id)
            if record is not None:
                record.completed_at = _now_from_record(record)
                record.response_status = 502
                record.response_headers_json = compact_json({"content-type": "application/json"})
                record.response_body = encoded_error
                record.response_content_type = "application/json"
                record.duration_ms = duration_ms
                record.error = str(exc)
        return JSONResponse(error_body, status_code=502)


def _build_upstream_url(upstream_base: str, path: str, query_string: str = "") -> str:
    base = upstream_base.rstrip("/") + "/"
    url = urljoin(base, path)
    if query_string:
        url = f"{url}?{query_string}"
    return url


def _headers_to_dict(headers: Any) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _forward_headers(headers: Any) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def _response_headers(headers: Any) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in RESPONSE_DROP_HEADERS
    }


def _is_stream_request(payload: Any | None, headers: Any) -> bool:
    if isinstance(payload, dict) and payload.get("stream") is True:
        return True
    accept = headers.get("accept", "")
    return "text/event-stream" in accept.lower()


@contextmanager
def _session(session_factory: SessionFactory):
    yield from session_scope(session_factory)


def _now_from_record(record: RequestRecord):
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=record.created_at.tzinfo)
