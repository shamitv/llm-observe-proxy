from __future__ import annotations

import json
import subprocess
import sys

import pytest
from sqlalchemy import inspect, text

from llm_observe_proxy import create_app
from llm_observe_proxy.admin import _stream_token_usage
from llm_observe_proxy.capture import extract_token_usage, has_tool_payload
from llm_observe_proxy.cli import resolve_bind
from llm_observe_proxy.config import (
    DEFAULT_INCOMING_HOST,
    DEFAULT_INCOMING_PORT,
    DEFAULT_UPSTREAM_URL,
    EXPOSED_INCOMING_HOST,
    Settings,
)
from llm_observe_proxy.database import (
    create_db_engine,
    create_session_factory,
    init_db,
    session_scope,
    set_incoming_server,
)
from llm_observe_proxy.rendering import render_payload


def test_app_factory_exposes_health_route() -> None:
    app = create_app()
    assert app.title == "LLM Observe Proxy"
    assert any(route.path == "/healthz" for route in app.routes)


def test_renderer_modes_for_json_text_markdown_tool_and_sse() -> None:
    json_render = render_payload(json.dumps({"ok": True}).encode(), "application/json", "auto")
    assert json_render.mode == "json"
    assert '"ok": true' in json_render.text

    markdown_render = render_payload(b"# Title\n\n- item", "text/plain", "auto")
    assert markdown_render.mode == "markdown"
    assert "<h1>Title</h1>" in markdown_render.html

    tool_body = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }
                    ]
                }
            }
        ]
    }
    tool_render = render_payload(json.dumps(tool_body).encode(), "application/json", "auto")
    assert tool_render.mode == "tool"
    assert tool_render.tool_blocks[0]["kind"] == "chat.tool_call"

    sse_render = render_payload(
        b'data: {"type":"response.output_text.delta","delta":"hi"}\n\ndata: [DONE]\n\n',
        "text/event-stream",
        "auto",
    )
    assert sse_render.mode == "sse"
    assert "data:" in sse_render.text


def test_renderer_text_mode_does_not_parse_sse_events(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("text mode should not parse SSE events")

    monkeypatch.setattr("llm_observe_proxy.rendering.decode_sse_json_events", fail_decode)

    rendered = render_payload(
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
        "text/event-stream",
        "text",
    )

    assert rendered.mode == "text"
    assert "data:" in rendered.text


def test_renderer_ignores_non_string_type_fields_in_nested_json() -> None:
    request_body = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "call a tool"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "query": {"type": "string"},
                        },
                    },
                },
            }
        ],
    }

    rendered = render_payload(json.dumps(request_body).encode(), "application/json", "json")

    assert rendered.mode == "json"
    assert '"lookup"' in rendered.text


def test_extract_token_usage_supports_chat_responses_and_responses_api() -> None:
    chat_usage = extract_token_usage(
        {"usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9}}
    )
    assert chat_usage.input_tokens == 6
    assert chat_usage.output_tokens == 3
    assert chat_usage.total_tokens == 9

    responses_usage = extract_token_usage(
        [{"response": {"usage": {"input_tokens": 8, "output_tokens": 4}}}]
    )
    assert responses_usage.input_tokens == 8
    assert responses_usage.output_tokens == 4
    assert responses_usage.total_tokens == 12


def test_stream_token_usage_reads_final_sse_usage_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("stream usage should use targeted final-event parsing")

    monkeypatch.setattr("llm_observe_proxy.admin.decode_sse_json_events", fail_decode)
    body = b"".join(
        [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":1000,'
            b'"completion_tokens":25,"total_tokens":1025}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    usage = _stream_token_usage(body)

    assert usage.input_tokens == 1000
    assert usage.output_tokens == 25
    assert usage.total_tokens == 1025


def test_tool_detector_ignores_non_string_type_fields() -> None:
    payload = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {"type": {"type": "string"}},
                    },
                },
            }
        ]
    }

    assert has_tool_payload(payload) is True


def test_module_cli_help_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "llm_observe_proxy", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Run the LLM Observe Proxy server" in completed.stdout
    assert "--expose-all-ips" in completed.stdout
    assert "--upstream-url" in completed.stdout
    assert "--models-file" in completed.stdout
    assert DEFAULT_INCOMING_HOST == "localhost"
    assert DEFAULT_INCOMING_PORT == 8080
    assert DEFAULT_UPSTREAM_URL == "http://localhost:8000/v1"


def test_cli_resolve_bind_uses_saved_incoming_settings(tmp_path) -> None:
    db_path = tmp_path / "proxy.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        set_incoming_server(session, 9090, True)
    engine.dispose()

    assert resolve_bind(None, None, False, settings) == (EXPOSED_INCOMING_HOST, 9090)
    assert resolve_bind("localhost", 7777, False, settings) == ("localhost", 7777)
    assert resolve_bind(None, None, True, settings) == (EXPOSED_INCOMING_HOST, 9090)


def test_init_db_upgrades_existing_sqlite_request_records_with_task_run_id(tmp_path) -> None:
    db_path = tmp_path / "old.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE request_records (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO request_records (id) VALUES (42)"))

    init_db(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("request_records")}
    indexes = {index["name"] for index in inspector.get_indexes("request_records")}
    with engine.connect() as connection:
        ids = connection.execute(text("SELECT id FROM request_records")).scalars().all()
    engine.dispose()

    assert "task_run_id" in columns
    assert "ix_request_records_task_run_id" in indexes
    assert ids == [42]
