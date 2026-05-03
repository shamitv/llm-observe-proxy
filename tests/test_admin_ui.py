from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from llm_observe_proxy.admin import templates
from llm_observe_proxy.app import create_app
from llm_observe_proxy.config import ModelRoute, Settings
from llm_observe_proxy.database import (
    ImageAsset,
    ModelPrice,
    ModelProvider,
    RequestRecord,
    TaskRun,
    upsert_model_price,
)

GLOBAL_UPSTREAM_URL = "http://localhost:8080/v1"
ROUTE_UPSTREAM_URL = "http://127.0.0.1:8080/v1"


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
    assert "TPS" in page.text
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


def test_settings_renders_model_routes_without_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_ROUTE_KEY", raising=False)
    app = _create_model_route_app(
        tmp_path,
        ModelRoute(
            model="local-qwen",
            upstream_url=ROUTE_UPSTREAM_URL,
            upstream_model="qwen3-coder-30b",
            api_key="direct-secret",
        ),
        ModelRoute(
            model="openai-mini",
            upstream_url="https://api.openai.com/v1",
            upstream_model="gpt-4.1-mini",
            api_key_env="MISSING_ROUTE_KEY",
        ),
    )

    with TestClient(app) as client:
        response = client.get("/admin/settings")

    assert response.status_code == 200
    assert "Model Routes" in response.text
    assert "local-qwen" in response.text
    assert "qwen3-coder-30b" in response.text
    assert "configured" in response.text
    assert "openai-mini" in response.text
    assert "MISSING_ROUTE_KEY" in response.text
    assert "missing" in response.text
    assert "direct-secret" not in response.text


def test_settings_manages_ui_model_routes(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    response = proxy_client.post(
        "/admin/settings/model-routes",
        data={
            "model": "local-ui",
            "upstream_url": ROUTE_UPSTREAM_URL,
            "upstream_model": "ui-upstream",
            "provider_slug": "openai",
            "api_key_env": "UI_ROUTE_KEY",
            "api_key": "direct-secret",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = proxy_client.get("/admin/settings")
    assert "local-ui" in settings.text
    assert "ui-upstream" in settings.text
    assert "OpenAI" in settings.text
    assert "UI_ROUTE_KEY" in settings.text
    assert "direct-secret" not in settings.text
    assert "Settings" in settings.text

    response = proxy_client.post(
        "/admin/settings/model-routes",
        data={
            "model": "local-ui",
            "upstream_url": ROUTE_UPSTREAM_URL,
            "upstream_model": "ui-updated",
            "provider_slug": "openai",
            "api_key_env": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = proxy_client.get("/admin/settings")
    assert "ui-updated" in updated.text
    assert "ui-upstream" not in updated.text

    response = proxy_client.post(
        "/admin/settings/model-routes/delete",
        data={"model": "local-ui"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    deleted = proxy_client.get("/admin/settings")
    assert "local-ui" not in deleted.text

    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "local-ui", "messages": [{"role": "user", "content": "hello"}]},
    )
    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.model_route is None


def test_settings_validates_ui_model_routes_against_startup_config(tmp_path: Path) -> None:
    app = _create_model_route_app(
        tmp_path,
        ModelRoute(model="locked-model", upstream_url=ROUTE_UPSTREAM_URL),
    )

    with TestClient(app) as client:
        blank = client.post(
            "/admin/settings/model-routes",
            data={"model": "   ", "upstream_url": ROUTE_UPSTREAM_URL},
        )
        invalid_url = client.post(
            "/admin/settings/model-routes",
            data={"model": "new-model", "upstream_url": "http://localhost:8080"},
        )
        duplicate = client.post(
            "/admin/settings/model-routes",
            data={"model": "locked-model", "upstream_url": ROUTE_UPSTREAM_URL},
        )
        delete_locked = client.post(
            "/admin/settings/model-routes/delete",
            data={"model": "locked-model"},
        )

    assert blank.status_code == 400
    assert "Model route model is required." in blank.text
    assert invalid_url.status_code == 400
    assert "Upstream URL must point to a /v1 base URL." in invalid_url.text
    assert duplicate.status_code == 400
    assert "Model route already exists in startup configuration." in duplicate.text
    assert delete_locked.status_code == 400
    assert "Startup configuration routes cannot be deleted from the UI." in delete_locked.text
    assert "Locked" in delete_locked.text


def test_ui_model_routes_persist_across_app_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "ui-routes.sqlite3"
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        upstream_url=GLOBAL_UPSTREAM_URL,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/admin/settings/model-routes",
            data={
                "model": "persisted-ui",
                "upstream_url": ROUTE_UPSTREAM_URL,
                "upstream_model": "persisted-upstream",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    with TestClient(create_app(settings)) as client:
        page = client.get("/admin/settings")

    assert page.status_code == 200
    assert "persisted-ui" in page.text
    assert "persisted-upstream" in page.text


def test_settings_manages_model_providers_and_prices(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    settings = proxy_client.get("/admin/settings")
    assert settings.status_code == 200
    assert "Model Providers" in settings.text
    assert "Model Pricing" in settings.text
    assert "OpenAI" in settings.text
    assert "gpt-5.4-mini" in settings.text

    invalid_provider = proxy_client.post(
        "/admin/settings/providers",
        data={"slug": "Bad Slug", "name": "Bad", "upstream_url": "", "currency": "USD"},
    )
    assert invalid_provider.status_code == 400
    assert "Provider slug must start" in invalid_provider.text

    response = proxy_client.post(
        "/admin/settings/providers",
        data={
            "slug": "custom",
            "name": "Custom Gateway",
            "upstream_url": "http://localhost:9000/v1/",
            "currency": "USD",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = proxy_client.post(
        "/admin/settings/model-prices",
        data={
            "provider_slug": "custom",
            "model": "custom-large",
            "display_name": "Custom Large",
            "aliases": "custom-alias",
            "input_usd_per_million": "1.25",
            "output_usd_per_million": "5",
            "active": "yes",
            "notes": "Local contract",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = proxy_client.get("/admin/settings")
    assert "Custom Gateway" in updated.text
    assert "http://localhost:9000/v1" in updated.text
    assert "custom-large" in updated.text
    assert "custom-alias" in updated.text
    assert "$1.25" in updated.text
    assert "$5.00" in updated.text

    with proxy_app.state.session_factory() as session:
        provider = session.get(ModelProvider, "custom")
        price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "custom",
                ModelPrice.model == "custom-large",
            )
        ).one()
        assert provider.upstream_url == "http://localhost:9000/v1"
        assert price.active is True

    response = proxy_client.post(
        "/admin/settings/model-prices/delete",
        data={"provider_slug": "custom", "model": "custom-large"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    response = proxy_client.post(
        "/admin/settings/providers/delete",
        data={"slug": "custom"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    deleted = proxy_client.get("/admin/settings")
    assert "custom-large" not in deleted.text
    assert "Custom Gateway" not in deleted.text


def test_settings_test_upstream_uses_configured_model_route(
    tmp_path: Path,
    fake_upstream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTE_KEY", "route-secret")
    app = _create_model_route_app(
        tmp_path,
        ModelRoute(
            model="local-qwen",
            upstream_url=ROUTE_UPSTREAM_URL,
            upstream_model="qwen3-coder-30b",
            api_key_env="ROUTE_KEY",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/settings/test-upstream",
            data={"test_kind": "simple", "model": "local-qwen", "prompt": "check route"},
        )

    assert response.status_code == 200
    assert "local-qwen" in response.text
    assert "qwen3-coder-30b" in response.text
    assert fake_upstream.last_request["path"] == "/v1/chat/completions"
    assert fake_upstream.last_request["body"]["model"] == "qwen3-coder-30b"
    assert fake_upstream.last_request["headers"]["authorization"] == "Bearer route-secret"


def test_settings_test_upstream_falls_back_for_unknown_model(
    tmp_path: Path,
    fake_upstream: Any,
) -> None:
    app = _create_model_route_app(
        tmp_path,
        ModelRoute(model="configured", upstream_url=ROUTE_UPSTREAM_URL),
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/settings/test-upstream",
            data={"test_kind": "simple", "model": "unknown", "prompt": "check fallback"},
        )

    assert response.status_code == 200
    assert "global fallback" in response.text
    assert fake_upstream.last_request["body"]["model"] == "unknown"


def test_settings_test_upstream_uses_ui_model_route(
    proxy_client: TestClient,
    fake_upstream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UI_ROUTE_KEY", "ui-secret")
    proxy_client.post(
        "/admin/settings/model-routes",
        data={
            "model": "local-ui",
            "upstream_url": ROUTE_UPSTREAM_URL,
            "upstream_model": "ui-upstream",
            "api_key_env": "UI_ROUTE_KEY",
        },
    )

    response = proxy_client.post(
        "/admin/settings/test-upstream",
        data={"test_kind": "simple", "model": "local-ui", "prompt": "check ui route"},
    )

    assert response.status_code == 200
    assert "local-ui" in response.text
    assert "ui-upstream" in response.text
    assert fake_upstream.last_request["body"]["model"] == "ui-upstream"
    assert fake_upstream.last_request["headers"]["authorization"] == "Bearer ui-secret"


def test_request_browser_and_detail_show_route_metadata(
    tmp_path: Path,
    fake_upstream: Any,
) -> None:
    app = _create_model_route_app(
        tmp_path,
        ModelRoute(
            model="local-qwen",
            upstream_url=ROUTE_UPSTREAM_URL,
            upstream_model="qwen3-coder-30b",
        ),
    )

    with TestClient(app) as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "local-qwen", "messages": [{"role": "user", "content": "hello"}]},
        )
        browser = client.get("/admin")
        detail = client.get("/admin/requests/1")

    assert fake_upstream.last_request["body"]["model"] == "qwen3-coder-30b"
    assert browser.status_code == 200
    assert "route-badge" in browser.text
    assert "local-qwen" in browser.text
    assert detail.status_code == 200
    assert "Upstream Model <strong>qwen3-coder-30b</strong>" in detail.text
    assert "Route <strong>local-qwen</strong>" in detail.text


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


def test_run_detail_shows_default_what_if_costs_without_mutating_snapshots(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post("/admin/runs/start", data={"name": "Default what-if"})
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )
    proxy_client.post("/admin/runs/end")

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        original_cost = record.billing_total_cost_usd

    detail = proxy_client.get("/admin/runs/1")

    assert detail.status_code == 200
    assert "What-if cost" in detail.text
    assert "GPT-5.5" in detail.text
    assert "GPT-5.4 Mini" in detail.text
    assert 'value="openai:gpt-5.5" checked' in detail.text
    assert 'value="openai:gpt-5.4-mini" checked' in detail.text
    assert "$0.000120" in detail.text
    assert "$0.000018" in detail.text
    assert "Missing Usage" in detail.text

    with proxy_app.state.session_factory() as session:
        record = session.scalars(select(RequestRecord)).one()
        assert record.billing_total_cost_usd == original_cost


def test_run_detail_accepts_repeated_what_if_params(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post("/admin/runs/start", data={"name": "Custom what-if"})
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )

    with proxy_app.state.session_factory() as session:
        upsert_model_price(
            session,
            provider_slug="openai",
            model="custom-low",
            display_name="Custom Low",
            input_usd_per_million="1",
            output_usd_per_million="2",
        )
        upsert_model_price(
            session,
            provider_slug="openai",
            model="custom-high",
            display_name="Custom High",
            input_usd_per_million="10",
            output_usd_per_million="20",
        )
        session.commit()

    detail = proxy_client.get(
        "/admin/runs/1?what_if=openai:custom-low&what_if=openai:custom-high"
    )

    assert detail.status_code == 200
    assert "Custom Low" in detail.text
    assert "Custom High" in detail.text
    assert 'value="openai:custom-low" checked' in detail.text
    assert 'value="openai:custom-high" checked' in detail.text
    assert 'value="openai:gpt-5.5" checked' not in detail.text
    assert "$0.000012" in detail.text
    assert "$0.000120" in detail.text


def test_run_detail_ignores_unknown_and_inactive_what_if_prices(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post("/admin/runs/start", data={"name": "Invalid what-if"})
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )

    with proxy_app.state.session_factory() as session:
        inactive = upsert_model_price(
            session,
            provider_slug="openai",
            model="inactive-price",
            display_name="Inactive Price",
            input_usd_per_million="1",
            output_usd_per_million="1",
            active=False,
        )
        inactive.active = False
        session.commit()

    detail = proxy_client.get(
        "/admin/runs/1?what_if=openai:inactive-price&what_if=openai:missing-price"
    )

    assert detail.status_code == 200
    assert "No active model prices matched the selected comparison." in detail.text
    assert "Inactive Price" not in detail.text


def test_admin_formats_large_numbers_and_durations(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    proxy_client.post("/admin/runs/start", data={"name": "Large totals"})
    proxy_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "inside"}]},
    )

    started = datetime(2026, 5, 1, tzinfo=UTC)
    with proxy_app.state.session_factory() as session:
        task_run = session.scalars(select(TaskRun)).one()
        record = session.scalars(select(RequestRecord)).one()
        task_run.started_at = started
        task_run.ended_at = started + timedelta(milliseconds=2_652_932)
        record.created_at = started
        record.completed_at = started + timedelta(milliseconds=2_579_395)
        record.duration_ms = 1_605_175
        record.response_body = json.dumps(
            {
                "usage": {
                    "prompt_tokens": 5_060_618,
                    "completion_tokens": 56_738,
                    "total_tokens": 5_117_356,
                }
            }
        ).encode()
        record.billing_input_tokens = 5_060_618
        record.billing_output_tokens = 56_738
        record.billing_total_tokens = 5_117_356
        session.commit()

    detail = proxy_client.get("/admin/runs/1")
    assert detail.status_code == 200
    assert "42m 59s" in detail.text
    assert "44m 13s" in detail.text
    assert "26m 45s" in detail.text
    assert ">5.06M<" in detail.text
    assert ">56.7k<" in detail.text
    assert ">5.12M<" in detail.text

    browser = proxy_client.get("/admin")
    assert "<strong>5.06M</strong><small>Input</small>" in browser.text
    assert "26m 45s" in browser.text


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


def _create_model_route_app(tmp_path: Path, *routes: ModelRoute) -> FastAPI:
    db_path = tmp_path / "admin-model-routes.sqlite3"
    return create_app(
        Settings(
            database_url=f"sqlite:///{db_path.as_posix()}",
            upstream_url=GLOBAL_UPSTREAM_URL,
            model_routes=routes,
        )
    )
