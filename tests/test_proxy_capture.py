from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from llm_observe_proxy.database import (
    ImageAsset,
    RequestRecord,
    end_active_task_run,
    session_scope,
    start_task_run,
)


def test_non_streaming_chat_completion_records_and_forwards_headers(
    proxy_client: TestClient,
    proxy_app: FastAPI,
    fake_upstream,
) -> None:
    response = proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer test-key", "X-Client-Request-Id": "trace-1"},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Plain chat response"
    assert fake_upstream.last_request["headers"]["authorization"] == "Bearer test-key"
    assert fake_upstream.last_request["headers"]["x-client-request-id"] == "trace-1"

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.endpoint == "/v1/chat/completions"
        assert record.model == "gpt-test"
        assert record.response_status == 200
        assert record.is_stream is False
        assert record.has_images is False
        assert record.has_tool_calls is False
        assert b"Plain chat response" in record.response_body


def test_requests_are_associated_with_active_task_run(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with session_scope(proxy_app.state.session_factory) as session:
        task_run = start_task_run(session, "Local benchmark")
        task_run_id = task_run.id

    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )

    with session_scope(proxy_app.state.session_factory) as session:
        end_active_task_run(session)

    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "outside"}]},
    )

    with proxy_app.state.session_factory() as session:
        records = session.scalars(select(RequestRecord).order_by(RequestRecord.id)).all()
        assert records[0].task_run_id == task_run_id
        assert records[1].task_run_id is None


def test_streaming_request_keeps_task_run_after_run_ends(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with session_scope(proxy_app.state.session_factory) as session:
        task_run = start_task_run(session, "Streaming benchmark")
        task_run_id = task_run.id

    with proxy_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "stream"}],
            "stream": True,
        },
    ) as response:
        with session_scope(proxy_app.state.session_factory) as session:
            end_active_task_run(session)
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert body.endswith(b"data: [DONE]\n\n")
    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.task_run_id == task_run_id
        assert record.is_stream is True


def test_responses_reasoning_payload_is_recorded_and_visible_in_ui(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    response = proxy_client.post(
        "/v1/responses",
        json={"model": "gpt-test", "input": "think carefully", "reasoning": {"effort": "medium"}},
    )

    assert response.status_code == 200
    assert response.json()["reasoning"]["effort"] == "medium"

    detail = proxy_client.get("/admin/requests/1?mode=json")
    assert detail.status_code == 200
    assert "Reasoned answer" in detail.text
    assert "reasoning" in detail.text

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.endpoint == "/v1/responses"
        assert record.model == "gpt-test"


def test_chat_streaming_captures_raw_sse(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "stream"}],
            "stream": True,
        },
    ) as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert b"data:" in body
    assert b"hello " in body
    assert body.endswith(b"data: [DONE]\n\n")

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.is_stream is True
        assert record.response_content_type.startswith("text/event-stream")
        assert record.response_body == body


def test_responses_streaming_tool_call_sets_tool_signal_and_ui_renderer(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_client.stream(
        "POST",
        "/v1/responses",
        json={
            "model": "gpt-test",
            "input": "weather",
            "stream": True,
            "tools": [{"type": "function", "name": "get_weather"}],
        },
    ) as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert b"function_call" in body

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.is_stream is True
        assert record.has_tool_calls is True

    detail = proxy_client.get("/admin/requests/1?mode=tool")
    assert detail.status_code == 200
    assert "get_weather" in detail.text
    assert "function_call" in detail.text


def test_images_are_extracted_from_data_urls_and_remote_urls(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    data_url = f"data:image/png;base64,{base64.b64encode(b'fake-png').decode()}"
    remote_url = "https://example.test/cat.png"

    response = proxy_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "image_url", "image_url": {"url": remote_url}},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        images = session.scalars(select(ImageAsset).order_by(ImageAsset.id)).all()
        assert record.has_images is True
        assert len(images) == 2
        assert images[0].source == data_url
        assert images[1].source == remote_url

    detail = proxy_client.get("/admin/requests/1")
    assert "Images Sent" in detail.text
    assert data_url in detail.text
    assert remote_url in detail.text


def test_tool_calls_render_for_non_streaming_chat_response(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    response = proxy_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "weather"}],
            "tools": [{"type": "function", "function": {"name": "get_weather"}}],
        },
    )

    assert response.status_code == 200
    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.has_tool_calls is True

    detail = proxy_client.get("/admin/requests/1?mode=tool")
    assert "chat.tool_call" in detail.text
    assert "get_weather" in detail.text


def test_generic_v1_passthrough_records_query_string(
    proxy_client: TestClient,
    proxy_app: FastAPI,
    fake_upstream,
) -> None:
    response = proxy_client.get("/v1/models?limit=2")

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "gpt-test"
    assert fake_upstream.last_request["query"] == "limit=2"

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.endpoint == "/v1/models"
        assert record.query_string == "limit=2"
