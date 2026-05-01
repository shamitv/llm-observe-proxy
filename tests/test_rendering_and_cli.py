from __future__ import annotations

import json
import subprocess
import sys

from llm_observe_proxy import create_app
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
