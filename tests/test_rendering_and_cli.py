from __future__ import annotations

import json
import subprocess
import sys

from llm_observe_proxy import create_app
from llm_observe_proxy.config import DEFAULT_UPSTREAM_URL
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


def test_module_cli_help_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "llm_observe_proxy", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Run the LLM Observe Proxy server" in completed.stdout
    assert "--upstream-url" in completed.stdout
    assert DEFAULT_UPSTREAM_URL == "http://localhost:8080/v1"
