from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_observe_proxy.capture import compact_json, extract_images
from llm_observe_proxy.config import Settings
from llm_observe_proxy.database import (
    ImageAsset,
    RequestRecord,
    create_db_engine,
    create_session_factory,
    init_db,
    session_scope,
    set_setting,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a demo SQLite DB for screenshots.")
    parser.add_argument("database", type=Path)
    args = parser.parse_args()

    if args.database.exists():
        args.database.unlink()
    args.database.parent.mkdir(parents=True, exist_ok=True)

    settings = Settings(database_url=f"sqlite:///{args.database.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        set_setting(session, "upstream_url", "http://localhost:8000/v1")
        _add_simple_chat(session)
        _add_tool_call(session)
        _add_image_request(session)
        _add_streaming_response(session)
    engine.dispose()


def _add_simple_chat(session) -> None:
    request_body = {
        "model": "gpt-demo",
        "messages": [{"role": "user", "content": "Summarize today's support queue."}],
    }
    response_body = {
        "id": "chatcmpl-demo-simple",
        "object": "chat.completion",
        "model": "gpt-demo",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "The queue is healthy: 12 open tickets, 3 escalations, "
                        "and no SLA breaches."
                    ),
                },
                "finish_reason": "stop",
            }
        ],
    }
    _add_record(session, 4, request_body, response_body)


def _add_tool_call(session) -> None:
    request_body = {
        "model": "gpt-demo",
        "messages": [{"role": "user", "content": "Check weather and calendar before booking."}],
        "tools": [
            {"type": "function", "function": {"name": "get_weather"}},
            {"type": "function", "function": {"name": "find_calendar_slot"}},
        ],
    }
    response_body = {
        "id": "chatcmpl-demo-tools",
        "object": "chat.completion",
        "model": "gpt-demo",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_weather",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": "{\"city\":\"Bengaluru\"}",
                            },
                        },
                        {
                            "id": "call_calendar",
                            "type": "function",
                            "function": {
                                "name": "find_calendar_slot",
                                "arguments": "{\"duration_minutes\":30}",
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    _add_record(session, 3, request_body, response_body, has_tool_calls=True)


def _add_image_request(session) -> None:
    chart = _svg_data_url("#147d75", "Chart")
    receipt = _svg_data_url("#b42318", "Receipt")
    request_body = {
        "model": "gpt-demo-vision",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Compare these two images."},
                    {"type": "image_url", "image_url": {"url": chart}},
                    {"type": "image_url", "image_url": {"url": receipt}},
                ],
            }
        ],
    }
    response_body = {
        "id": "chatcmpl-demo-images",
        "object": "chat.completion",
        "model": "gpt-demo-vision",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "The first image is a dashboard chart; the second is a "
                        "receipt-like document."
                    ),
                },
                "finish_reason": "stop",
            }
        ],
    }
    _add_record(session, 2, request_body, response_body)


def _add_streaming_response(session) -> None:
    request_body = {
        "model": "gpt-demo",
        "stream": True,
        "messages": [{"role": "user", "content": "Stream a short release note."}],
    }
    response_body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Release "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"ready."}}]}\n\n'
        "data: [DONE]\n\n"
    )
    _add_record(
        session,
        1,
        request_body,
        response_body.encode("utf-8"),
        response_content_type="text/event-stream",
        is_stream=True,
    )


def _add_record(
    session,
    age_minutes: int,
    request_payload: dict,
    response_payload: dict | bytes,
    *,
    response_content_type: str = "application/json",
    is_stream: bool = False,
    has_tool_calls: bool = False,
) -> None:
    request_body = json.dumps(request_payload).encode("utf-8")
    response_body = (
        response_payload
        if isinstance(response_payload, bytes)
        else json.dumps(response_payload, ensure_ascii=False, indent=2).encode("utf-8")
    )
    images = extract_images(request_payload)
    created_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    record = RequestRecord(
        created_at=created_at,
        completed_at=created_at + timedelta(milliseconds=240),
        method="POST",
        path="/v1/chat/completions",
        query_string="",
        endpoint="/v1/chat/completions",
        model=request_payload.get("model"),
        upstream_url="http://localhost:8000/v1/chat/completions",
        request_headers_json=compact_json({"content-type": "application/json"}),
        request_body=request_body,
        request_content_type="application/json",
        response_status=200,
        response_headers_json=compact_json({"content-type": response_content_type}),
        response_body=response_body,
        response_content_type=response_content_type,
        duration_ms=240 + age_minutes,
        is_stream=is_stream,
        has_images=bool(images),
        has_tool_calls=has_tool_calls,
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


def _svg_data_url(color: str, label: str) -> str:
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="640" height="420">
      <rect width="640" height="420" rx="32" fill="{color}"/>
      <text x="320" y="230" text-anchor="middle" font-size="54"
            font-family="Arial, sans-serif" fill="white">{label}</text>
    </svg>
    """.strip()
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


if __name__ == "__main__":
    main()
