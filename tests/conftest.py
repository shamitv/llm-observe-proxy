from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from llm_observe_proxy.app import create_app
from llm_observe_proxy.config import Settings

UPSTREAM_URL = "http://localhost:8080/v1"


class FakeUpstreamState:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.requests.clear()

    @property
    def last_request(self) -> dict[str, Any]:
        return self.requests[-1]


@pytest.fixture(scope="session")
def fake_upstream() -> Iterator[FakeUpstreamState]:
    state = FakeUpstreamState()
    app = _build_upstream_app(state)
    _assert_port_available(8080)
    config = uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_upstream()
    try:
        yield state
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def reset_fake_upstream(fake_upstream: FakeUpstreamState) -> Iterator[None]:
    fake_upstream.reset()
    yield
    fake_upstream.reset()


@pytest.fixture
def proxy_app(tmp_path: Path) -> Iterator[FastAPI]:
    db_path = tmp_path / "proxy.sqlite3"
    app = create_app(
        Settings(database_url=f"sqlite:///{db_path.as_posix()}", upstream_url=UPSTREAM_URL)
    )
    yield app


@pytest.fixture
def proxy_client(proxy_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(proxy_app) as client:
        yield client


def _build_upstream_app(state: FakeUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def handle_v1(path: str, request: Request):
        body = await request.body()
        payload = _json_or_none(body)
        state.requests.append(
            {
                "method": request.method,
                "path": f"/v1/{path}",
                "query": request.url.query,
                "headers": dict(request.headers),
                "body": payload,
            }
        )

        if path == "models":
            return {"object": "list", "data": [{"id": "gpt-test", "object": "model"}]}

        if isinstance(payload, dict) and payload.get("force_status"):
            return JSONResponse(
                {"error": {"message": "forced failure", "type": "fake_upstream"}},
                status_code=int(payload["force_status"]),
            )

        if isinstance(payload, dict) and payload.get("stream") is True:
            return StreamingResponse(
                _streaming_chunks(path, payload),
                media_type="text/event-stream",
            )

        if path == "responses":
            return _responses_payload(payload)

        return _chat_payload(payload)

    return app


async def _streaming_chunks(path: str, payload: dict[str, Any]):
    if path == "responses":
        chunks = [
            {"type": "response.created", "response": {"id": "resp_stream"}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": "{\"location\":\"Paris\"}",
                },
            },
            {"type": "response.completed", "response": {"id": "resp_stream"}},
        ]
    else:
        chunks = [
            {"id": "chat_stream", "choices": [{"delta": {"role": "assistant"}}]},
            {"id": "chat_stream", "choices": [{"delta": {"content": "hello "}}]},
            {"id": "chat_stream", "choices": [{"delta": {"content": "stream"}}]},
        ]
    for chunk in chunks:
        yield f"data: {json.dumps(chunk)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def _responses_payload(payload: Any) -> dict[str, Any]:
    model = payload.get("model", "gpt-test") if isinstance(payload, dict) else "gpt-test"
    if isinstance(payload, dict) and payload.get("tools"):
        return {
            "id": "resp_tool",
            "object": "response",
            "model": model,
            "output": [
                {
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": "{\"location\":\"Paris\"}",
                }
            ],
        }
    return {
        "id": "resp_reasoning",
        "object": "response",
        "model": model,
        "reasoning": {"effort": "medium", "summary": "short chain of thought summary"},
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Reasoned answer"}],
            }
        ],
        "output_text": "Reasoned answer",
    }


def _chat_payload(payload: Any) -> dict[str, Any]:
    model = payload.get("model", "gpt-test") if isinstance(payload, dict) else "gpt-test"
    if isinstance(payload, dict) and payload.get("tools"):
        return {
            "id": "chat_tool",
            "object": "chat.completion",
            "model": model,
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
                                    "arguments": "{\"location\":\"Paris\"}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
    if isinstance(payload, dict) and payload.get("metadata", {}).get("markdown"):
        content = "# Run Report\n\n- captured\n- rendered"
    else:
        content = "Plain chat response"
    return {
        "id": "chat_plain",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


def _json_or_none(body: bytes) -> Any | None:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _wait_for_upstream() -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get("http://localhost:8080/healthz", timeout=0.5)
            if response.status_code == 200:
                return
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"fake upstream did not start: {last_error}")


def _assert_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            pytest.fail(f"localhost:{port} is already in use; tests require that upstream port.")
