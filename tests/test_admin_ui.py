from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from llm_observe_proxy.admin import templates
from llm_observe_proxy.database import ImageAsset, RequestRecord, TaskRun


def test_request_browser_filters_and_markdown_renderer(proxy_client: TestClient) -> None:
    proxy_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "metadata": {"markdown": True},
            "messages": [{"role": "user", "content": "report"}],
        },
    )

    page = proxy_client.get("/admin?model=gpt-test")
    assert page.status_code == 200
    assert "Request Browser" in page.text
    assert "gpt-test" in page.text
    assert "/v1/chat/completions" in page.text
    assert "Tokens" in page.text
    assert "<strong>6</strong><small>Input</small>" in page.text
    assert "<strong>3</strong><small>Output</small>" in page.text
    assert "<strong>9</strong><small>Total</small>" in page.text

    detail = proxy_client.get("/admin/requests/1?mode=markdown")
    assert detail.status_code == 200
    assert "<h1>Run Report</h1>" in detail.text
    assert "<li>captured</li>" in detail.text


def test_settings_updates_upstream_url(proxy_client: TestClient, proxy_app: FastAPI) -> None:
    response = proxy_client.post(
        "/admin/settings/upstream",
        data={"upstream_url": "http://localhost:8080/v1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = proxy_client.get("/admin/settings")
    assert "http://localhost:8080/v1" in settings.text

    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
    )
    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.upstream_url == "http://localhost:8080/v1/chat/completions"


def test_runs_require_name_and_manage_active_state(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    blank = proxy_client.post("/admin/runs/start", data={"name": "   "})
    assert blank.status_code == 400
    assert "Run name is required." in blank.text

    response = proxy_client.post(
        "/admin/runs/start",
        data={"name": "Video benchmark"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    runs_page = proxy_client.get("/admin/runs")
    assert "Run in progress" in runs_page.text
    assert "Video benchmark" in runs_page.text

    response = proxy_client.post(
        "/admin/runs/start",
        data={"name": "Cloud comparison"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with proxy_app.state.session_factory() as session:
        runs = session.scalars(select(TaskRun).order_by(TaskRun.id)).all()
        assert [run.name for run in runs] == ["Video benchmark", "Cloud comparison"]
        assert runs[0].ended_at is not None
        assert runs[1].ended_at is None

    response = proxy_client.post("/admin/runs/end", follow_redirects=False)
    assert response.status_code == 303
    with proxy_app.state.session_factory() as session:
        active = session.scalars(select(TaskRun).where(TaskRun.ended_at.is_(None))).all()
        assert active == []


def test_run_filter_detail_and_badges_show_associated_requests(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post("/admin/runs/start", data={"name": "Local video task"})
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )
    proxy_client.post("/admin/runs/end")
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "outside"}]},
    )

    with proxy_app.state.session_factory() as session:
        task_run = session.scalars(select(TaskRun)).one()
        records = session.scalars(select(RequestRecord).order_by(RequestRecord.id)).all()
        assert records[0].task_run_id == task_run.id
        assert records[1].task_run_id is None

    browser = proxy_client.get(f"/admin?run={task_run.id}")
    assert browser.status_code == 200
    assert "Local video task" in browser.text
    assert "#1" in browser.text
    assert "#2" not in browser.text

    detail = proxy_client.get(f"/admin/runs/{task_run.id}")
    assert detail.status_code == 200
    assert "LLM wall time" in detail.text
    assert "Total tokens" in detail.text
    assert ">9<" in detail.text
    assert "Run traffic" in detail.text
    assert "#1" in detail.text
    assert "#2" not in detail.text

    request_detail = proxy_client.get("/admin/requests/1")
    assert (
        "Run <strong><a href=\"/admin/runs/1\">Local video task</a></strong>"
        in request_detail.text
    )


def test_settings_updates_incoming_server(proxy_client: TestClient) -> None:
    settings = proxy_client.get("/admin/settings")
    assert settings.status_code == 200
    assert "Incoming Server" in settings.text
    assert "localhost:8080" in settings.text

    response = proxy_client.post(
        "/admin/settings/incoming",
        data={"incoming_port": "9090", "expose_all_ips": "yes"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = proxy_client.get("/admin/settings")
    assert "0.0.0.0:9090" in updated.text
    assert 'name="expose_all_ips" value="yes" checked' in updated.text


def test_settings_template_defaults_incoming_port_when_context_is_missing() -> None:
    rendered = templates.env.get_template("settings.html").render(
        page_title="Settings",
        total=0,
        trim_count=0,
        days=30,
        upstream_url="http://localhost:8000/v1",
        error=None,
        url_for=lambda _name, path: f"/admin/static{path}",
    )

    assert "localhost:8080" in rendered
    assert 'name="incoming_port" value="8080"' in rendered


def test_settings_rejects_invalid_incoming_port(proxy_client: TestClient) -> None:
    response = proxy_client.post(
        "/admin/settings/incoming",
        data={"incoming_port": "70000"},
    )

    assert response.status_code == 400
    assert "Incoming port must be between 1 and 65535." in response.text


def test_settings_rejects_invalid_upstream_url(proxy_client: TestClient) -> None:
    response = proxy_client.post(
        "/admin/settings/upstream",
        data={"upstream_url": "http://localhost:8080"},
    )

    assert response.status_code == 400
    assert "must point to a /v1 base URL" in response.text


@pytest.mark.parametrize(
    ("test_kind", "expected_content"),
    [
        ("simple", "check simple"),
        ("image", "check image"),
        ("tools", "check tools"),
    ],
)
def test_settings_test_upstream_sends_sample_payloads(
    proxy_client: TestClient,
    fake_upstream: Any,
    test_kind: str,
    expected_content: str,
) -> None:
    response = proxy_client.post(
        "/admin/settings/test-upstream",
        data={"test_kind": test_kind, "model": "gpt-test", "prompt": expected_content},
    )

    assert response.status_code == 200
    assert "Test Upstream" in response.text
    assert "Plain chat response" in response.text or "call_weather" in response.text

    request = fake_upstream.last_request
    assert request["method"] == "POST"
    assert request["path"] == "/v1/chat/completions"
    assert request["body"]["model"] == "gpt-test"

    user_content = request["body"]["messages"][0]["content"]
    if test_kind == "image":
        assert user_content[0] == {"type": "text", "text": expected_content}
        assert user_content[1]["type"] == "image_url"
        assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    else:
        assert user_content == expected_content

    if test_kind == "tools":
        tool = request["body"]["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "get_weather"
    else:
        assert "tools" not in request["body"]


def test_settings_test_upstream_rejects_invalid_kind(proxy_client: TestClient) -> None:
    response = proxy_client.post(
        "/admin/settings/test-upstream",
        data={"test_kind": "bad", "model": "gpt-test", "prompt": "hello"},
    )

    assert response.status_code == 400
    assert "Choose a valid upstream test" in response.text


def test_trim_deletes_records_older_than_requested_days(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "new"}]},
    )
    proxy_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-test",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                        }
                    ],
                }
            ],
        },
    )

    with proxy_app.state.session_factory() as session:
        old_record = session.get(RequestRecord, 2)
        old_record.created_at = datetime.now(UTC) - timedelta(days=45)
        session.commit()

    settings = proxy_client.get("/admin/settings?days=30")
    assert "Older than 30 days" in settings.text
    assert ">1<" in settings.text

    response = proxy_client.post(
        "/admin/trim",
        data={"days": "30", "confirm": "yes"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with proxy_app.state.session_factory() as session:
        records = session.scalars(select(RequestRecord).order_by(RequestRecord.id)).all()
        images = session.scalars(select(ImageAsset)).all()
        assert [record.id for record in records] == [1]
        assert images == []
