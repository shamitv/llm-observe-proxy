from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from llm_observe_proxy.admin import templates
from llm_observe_proxy.app import create_app
from llm_observe_proxy.compatibility import QWEN_TAGGED_TOOL_CALL_REWRITE
from llm_observe_proxy.config import ModelRoute, Settings
from llm_observe_proxy.database import (
    ImageAsset,
    ModelPrice,
    ModelProvider,
    RequestRecord,
    TaskRun,
    upsert_model_price,
    upsert_model_price_tier,
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


def test_request_browser_paginates_records(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        started = datetime(2026, 5, 1, tzinfo=UTC)
        for index in range(55):
            _add_request_record(
                session,
                created_at=started + timedelta(minutes=index),
                model="page-model",
            )
        session.commit()

    first_page = proxy_client.get("/admin")
    assert first_page.status_code == 200
    assert "Showing <strong>1-50</strong>" in first_page.text
    assert "of <strong>55</strong>" in first_page.text
    assert 'href="/admin/requests/55">#55</a>' in first_page.text
    assert 'href="/admin/requests/6">#6</a>' in first_page.text
    assert 'href="/admin/requests/5">#5</a>' not in first_page.text
    assert "Next" in first_page.text

    second_page = proxy_client.get("/admin?page=2")
    assert second_page.status_code == 200
    assert "Showing <strong>51-55</strong>" in second_page.text
    assert "of <strong>55</strong>" in second_page.text
    assert 'href="/admin/requests/5">#5</a>' in second_page.text
    assert 'href="/admin/requests/1">#1</a>' in second_page.text
    assert 'href="/admin/requests/6">#6</a>' not in second_page.text
    assert "Previous" in second_page.text


def test_request_browser_pagination_preserves_filters(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        started = datetime(2026, 5, 1, tzinfo=UTC)
        for index in range(3):
            _add_request_record(
                session,
                created_at=started + timedelta(minutes=index),
                model="target-model",
            )
        _add_request_record(session, created_at=started, model="other-model")
        session.commit()

    page = proxy_client.get("/admin?model=target-model&per_page=1")

    assert page.status_code == 200
    assert "Showing <strong>1-1</strong>" in page.text
    assert "of <strong>3</strong>" in page.text
    assert "model=target-model" in page.text
    assert "per_page=1" in page.text
    assert "page=2" in page.text
    assert "<span>other-model</span>" not in page.text


def test_pending_requests_show_elapsed_duration(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        pending = _add_request_record(
            session,
            created_at=datetime.now(UTC) - timedelta(minutes=5),
            model="slow-model",
            completed=False,
            input_tokens=None,
            output_tokens=None,
            estimated_input_tokens=50_100,
        )
        completed = _add_request_record(
            session,
            created_at=datetime.now(UTC) - timedelta(minutes=1),
            model="done-model",
            estimated_input_tokens=100_000,
        )
        session.commit()
        pending_id = pending.id
        completed_id = completed.id

    browser = proxy_client.get("/admin")

    assert browser.status_code == 200
    assert 'class="elapsed-duration" data-pending-start="' in browser.text
    assert "so far</span>" in browser.text
    assert (
        '<span class="estimated-token"><strong>~50.1k</strong>'
        "<small>Est. input</small></span>"
    ) in browser.text
    assert "pending" in browser.text
    assert f'href="/admin/requests/{completed_id}">#{completed_id}</a>' in browser.text
    assert "~100k" not in browser.text
    assert "1 s" in browser.text

    detail = proxy_client.get(f"/admin/requests/{pending_id}")
    assert detail.status_code == 200
    assert "Duration <strong><span class=\"elapsed-duration\"" in detail.text
    assert "so far</span>" in detail.text
    assert "Status <strong>pending</strong>" in detail.text
    assert "~50.1k" in detail.text
    assert "Estimate tokenizer" in detail.text


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
            "fixes": QWEN_TAGGED_TOOL_CALL_REWRITE,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = proxy_client.get("/admin/settings")
    assert "local-ui" in settings.text
    assert "ui-upstream" in settings.text
    assert "OpenAI" in settings.text
    assert "UI_ROUTE_KEY" in settings.text
    assert QWEN_TAGGED_TOOL_CALL_REWRITE in settings.text
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
            "fixes": "",
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
        invalid_fix = client.post(
            "/admin/settings/model-routes",
            data={
                "model": "new-model",
                "upstream_url": ROUTE_UPSTREAM_URL,
                "fixes": "unknown-fix",
            },
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
    assert invalid_fix.status_code == 400
    assert "Unknown compatibility fix" in invalid_fix.text
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
                "fixes": QWEN_TAGGED_TOOL_CALL_REWRITE,
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    with TestClient(create_app(settings)) as client:
        page = client.get("/admin/settings")

    assert page.status_code == 200
    assert "persisted-ui" in page.text
    assert "persisted-upstream" in page.text
    assert QWEN_TAGGED_TOOL_CALL_REWRITE in page.text


def test_default_compat_fixes_display_validate_and_persist(tmp_path: Path) -> None:
    db_path = tmp_path / "compat-fixes.sqlite3"
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        upstream_url=GLOBAL_UPSTREAM_URL,
    )

    with TestClient(create_app(settings)) as client:
        page = client.get("/admin/settings")
        invalid = client.post(
            "/admin/settings/compat-fixes",
            data={"fixes": "qwen-tagged-tool-call-rewrite, qwen-tagged-tool-call-rewrite"},
        )
        saved = client.post(
            "/admin/settings/compat-fixes",
            data={"fixes": f"\n{QWEN_TAGGED_TOOL_CALL_REWRITE}\n"},
            follow_redirects=False,
        )

    assert page.status_code == 200
    assert "Default Compatibility Fixes" in page.text
    assert "Promote complete Qwen" in page.text
    assert invalid.status_code == 400
    assert "Duplicate compatibility fix" in invalid.text
    assert saved.status_code == 303

    with TestClient(create_app(settings)) as client:
        restarted = client.get("/admin/settings")

    assert restarted.status_code == 200
    assert QWEN_TAGGED_TOOL_CALL_REWRITE in restarted.text


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
            "cached_input_usd_per_million": "0.25",
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
    assert "$0.2500" in updated.text
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
        assert price.cached_input_usd_per_million == Decimal("0.250000")
        price_id = price.id

    response = proxy_client.post(
        "/admin/settings/model-price-tiers",
        data={
            "model_price_id": str(price_id),
            "label": "Short context",
            "min_input_tokens": "",
            "max_input_tokens": "1000",
            "input_usd_per_million": "0.75",
            "cached_input_usd_per_million": "0.075",
            "output_usd_per_million": "2.50",
            "source_url": "https://example.com/custom-pricing",
            "checked_at": "2026-05-23",
            "release_date": "2026-01-15",
            "notes": "Tier note",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = proxy_client.get("/admin/settings")
    assert "Short context" in updated.text
    assert "0-999 input tokens" in updated.text
    assert "$0.0750" in updated.text
    assert "https://example.com/custom-pricing" not in updated.text

    with proxy_app.state.session_factory() as session:
        price = session.get(ModelPrice, price_id)
        tier_id = price.tiers[0].id
        assert price.tiers[0].label == "Short context"
        assert price.tiers[0].max_input_tokens == 1000

    invalid_tier = proxy_client.post(
        "/admin/settings/model-price-tiers",
        data={
            "model_price_id": str(price_id),
            "min_input_tokens": "999",
            "max_input_tokens": "1200",
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
        },
    )
    assert invalid_tier.status_code == 400
    assert "overlaps" in invalid_tier.text

    response = proxy_client.post(
        "/admin/settings/model-price-tiers/delete",
        data={"tier_id": str(tier_id)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = proxy_client.get("/admin/settings")
    assert "Short context" not in updated.text
    assert "Scalar only" in updated.text

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


def test_run_detail_uses_compact_header_for_active_run(proxy_client: TestClient) -> None:
    response = proxy_client.post(
        "/admin/runs/start",
        data={"name": "Live compact task", "notes": "watching a local model"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = proxy_client.get("/admin/runs/1")

    assert detail.status_code == 200
    assert 'class="run-summary-header"' in detail.text
    assert 'class="run-control"' not in detail.text
    assert 'class="kpi-grid"' not in detail.text
    assert "Run in progress" in detail.text
    assert "Run: Live compact task" in detail.text
    assert "watching a local model" in detail.text
    assert "Started <strong>" in detail.text
    assert "Ended <strong>active</strong>" in detail.text
    assert "Requests" in detail.text
    assert "LLM wall time" in detail.text
    assert "Output tok/s" in detail.text
    assert "End run" in detail.text
    assert detail.text.index("run-summary-header") < detail.text.index("What-if cost")
    assert 'data-api-url="/admin/api/runs/1/what-if"' in detail.text
    assert "Models/providers like OpenAI, Anthropic, Gemini, Qwen" in detail.text
    assert 'type="checkbox" name="what_if"' not in detail.text
    assert 'class="what-if-options"' not in detail.text


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
    assert 'class="run-summary-header"' in detail.text
    assert 'class="run-control"' not in detail.text
    assert 'class="kpi-grid"' not in detail.text
    assert "LLM wall time" in detail.text
    assert "Total tokens" in detail.text
    assert ">9<" in detail.text
    assert "Run traffic" in detail.text
    assert "End run" not in detail.text
    assert "#1" in detail.text
    assert "#2" not in detail.text

    request_detail = proxy_client.get("/admin/requests/1")
    assert (
        "Run <strong><a href=\"/admin/runs/1\">Local video task</a></strong>"
        in request_detail.text
    )


def test_run_detail_paginates_traffic_without_limiting_what_if_totals(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        price = upsert_model_price(
            session,
            provider_slug="openai",
            model="custom-full-run",
            display_name="Custom Full Run",
            input_usd_per_million="1",
            cached_input_usd_per_million="0.1",
            output_usd_per_million="2",
        )
        task_run = TaskRun(name="Large run", started_at=datetime(2026, 5, 1, tzinfo=UTC))
        session.add(task_run)
        session.flush()
        started = task_run.started_at
        for index in range(55):
            _add_request_record(
                session,
                created_at=started + timedelta(minutes=index),
                model=price.model,
                task_run_id=task_run.id,
                input_tokens=1000,
                cached_input_tokens=800,
                output_tokens=500,
            )
        session.commit()
        run_id = task_run.id

    detail = proxy_client.get(f"/admin/runs/{run_id}?per_page=10")

    assert detail.status_code == 200
    assert "Showing <strong>1-10</strong>" in detail.text
    assert "of <strong>55</strong>" in detail.text
    assert "#55" in detail.text
    assert "#46" in detail.text
    assert "#45" not in detail.text
    assert "Custom Full Run" not in detail.text

    api = proxy_client.get(
        f"/admin/api/runs/{run_id}/what-if?key=openai:custom-full-run"
    )
    data = api.json()
    assert api.status_code == 200
    assert data["selected_keys"] == ["openai:custom-full-run"]
    assert data["compared_count"] == 1
    scenario = data["scenarios"][0]
    assert scenario["label"] == "Custom Full Run"
    assert scenario["display"]["total_cost_usd"] == "$0.0704"
    assert scenario["display"]["cached_input_tokens"] == "44k"
    assert scenario["included_request_count"] == 55


def test_run_detail_marks_mixed_tier_what_if_rates(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        price = upsert_model_price(
            session,
            provider_slug="openai",
            model="tiered-run",
            display_name="Tiered Run",
            input_usd_per_million="9",
            output_usd_per_million="9",
        )
        upsert_model_price_tier(
            session,
            model_price_id=price.id,
            max_input_tokens="1000",
            input_usd_per_million="1",
            output_usd_per_million="2",
            label="short",
        )
        upsert_model_price_tier(
            session,
            model_price_id=price.id,
            min_input_tokens="1000",
            input_usd_per_million="3",
            output_usd_per_million="6",
            label="long",
        )
        task_run = TaskRun(name="Tiered run", started_at=datetime(2026, 5, 1, tzinfo=UTC))
        session.add(task_run)
        session.flush()
        _add_request_record(
            session,
            created_at=task_run.started_at,
            model=price.model,
            task_run_id=task_run.id,
            input_tokens=999,
            output_tokens=100,
        )
        _add_request_record(
            session,
            created_at=task_run.started_at + timedelta(seconds=1),
            model=price.model,
            task_run_id=task_run.id,
            input_tokens=1000,
            output_tokens=100,
        )
        session.commit()
        run_id = task_run.id

    api = proxy_client.get(f"/admin/api/runs/{run_id}/what-if?key=openai:tiered-run")
    data = api.json()

    assert api.status_code == 200
    scenario = data["scenarios"][0]
    assert scenario["label"] == "Tiered Run"
    assert scenario["display"]["input_usd_per_million"] == "Mixed tiers"
    assert scenario["display"]["output_usd_per_million"] == "Mixed tiers"
    assert scenario["display"]["total_cost_usd"] == "$0.004799"


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
    assert 'data-api-url="/admin/api/runs/1/what-if"' in detail.text
    assert 'data-what-if-input' in detail.text
    assert 'data-what-if-options' in detail.text
    assert "Loading comparisons..." in detail.text
    assert "Models/providers like OpenAI, Anthropic, Gemini, Qwen" in detail.text
    assert 'type="checkbox" name="what_if"' not in detail.text
    assert "GPT-5.5" not in detail.text
    assert "GPT-5.4 Mini" not in detail.text
    assert "Missing Usage" in detail.text

    api = proxy_client.get("/admin/api/runs/1/what-if")
    data = api.json()

    assert api.status_code == 200
    assert data["selected_keys"] == ["openai:gpt-5.5", "openai:gpt-5.4-mini"]
    assert data["compared_count"] == 2
    labels = [scenario["label"] for scenario in data["scenarios"]]
    assert labels == ["GPT-5.5", "GPT-5.4 Mini"]
    totals = [scenario["display"]["total_cost_usd"] for scenario in data["scenarios"]]
    assert totals == ["$0.000120", "$0.000018"]
    option_labels = {option["label"] for option in data["options"]}
    assert "GPT-5.5" in option_labels
    assert "GPT-5.4 Mini" in option_labels

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

    api = proxy_client.get(
        "/admin/api/runs/1/what-if?key=openai:custom-low&key=openai:custom-high"
    )
    data = api.json()

    assert api.status_code == 200
    assert data["selected_keys"] == ["openai:custom-low", "openai:custom-high"]
    assert [scenario["label"] for scenario in data["scenarios"]] == [
        "Custom Low",
        "Custom High",
    ]
    assert [scenario["display"]["total_cost_usd"] for scenario in data["scenarios"]] == [
        "$0.000012",
        "$0.000120",
    ]


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

    api = proxy_client.get(
        "/admin/api/runs/1/what-if?key=openai:inactive-price&key=openai:missing-price"
    )
    data = api.json()

    assert api.status_code == 200
    assert data["message"] == "No active model prices matched the selected comparison."
    assert data["selected_keys"] == []
    assert data["scenarios"] == []
    assert "Inactive Price" not in json.dumps(data)


def test_run_what_if_api_returns_json_404_for_missing_run(
    proxy_client: TestClient,
) -> None:
    response = proxy_client.get("/admin/api/runs/999/what-if")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found."}


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
    assert 'datetime="2026-05-01T00:00:00.000000Z" data-local-time="full"' in detail.text
    assert "2026-05-01 00:00:00 UTC" in detail.text
    assert ">5.06M<" in detail.text
    assert ">56.7k<" in detail.text
    assert ">5.12M<" in detail.text
    assert ">35.35<" in detail.text

    runs = proxy_client.get("/admin/runs")
    assert ">35.35<" in runs.text
    assert 'data-local-time="table">2026-05-01 00:00:00 UTC</time>' in runs.text
    browser = proxy_client.get("/admin")
    assert "<strong>5.06M</strong><small>Input</small>" in browser.text
    assert "26m 45s" in browser.text
    assert 'data-local-time="table">2026-05-01 00:00:00 UTC</time>' in browser.text

    request_detail = proxy_client.get("/admin/requests/1")
    assert "Created <strong><time" in request_detail.text
    assert "Completed <strong><time" in request_detail.text
    assert 'data-local-time="full">2026-05-01 00:00:00 UTC</time>' in request_detail.text


def test_admin_reads_timings_usage_for_existing_stream_records(
    proxy_client: TestClient,
    proxy_app: FastAPI,
) -> None:
    with proxy_app.state.session_factory() as session:
        record = _add_request_record(
            session,
            created_at=datetime.now(UTC),
            input_tokens=None,
            output_tokens=None,
        )
        record.is_stream = True
        record.response_content_type = "text/event-stream"
        record.response_body = (
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            b'data: {"choices":[{"finish_reason":"stop","index":0,"delta":{}}],'
            b'"timings":{"cache_n":0,"prompt_n":1185,"predicted_n":40}}\n\n'
            b"data: [DONE]\n\n"
        )
        session.commit()
        record_id = record.id

    browser = proxy_client.get("/admin")
    assert browser.status_code == 200
    assert "<strong>1.19k</strong><small>Input</small>" in browser.text
    assert "<strong>40</strong><small>Output</small>" in browser.text
    assert "<strong>1.23k</strong><small>Total</small>" in browser.text

    detail = proxy_client.get(f"/admin/requests/{record_id}")
    assert detail.status_code == 200
    assert "<strong>1.19k</strong>Input tokens" in detail.text
    assert "<strong>40</strong>Output tokens" in detail.text
    assert "<strong>1.23k</strong>Total tokens" in detail.text


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


def _add_request_record(
    session,
    *,
    created_at: datetime,
    model: str = "gpt-test",
    task_run_id: int | None = None,
    input_tokens: int | None = 6,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = 3,
    completed: bool = True,
    estimated_input_tokens: int | None = None,
) -> RequestRecord:
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    record = RequestRecord(
        task_run_id=task_run_id,
        created_at=created_at,
        completed_at=created_at + timedelta(seconds=1) if completed else None,
        method="POST",
        path="/v1/chat/completions",
        query_string="",
        endpoint="/v1/chat/completions",
        model=model,
        upstream_url=f"{GLOBAL_UPSTREAM_URL}/chat/completions",
        request_headers_json="{}",
        request_body=b"{}",
        request_content_type="application/json",
        response_status=200 if completed else None,
        response_headers_json="{}" if completed else None,
        response_body=b"{}" if completed else None,
        response_content_type="application/json" if completed else None,
        duration_ms=1000 if completed else None,
        billing_provider_slug="openai",
        billing_provider_name="OpenAI",
        billing_model=model,
        billing_input_tokens=input_tokens,
        billing_cached_input_tokens=cached_input_tokens,
        billing_output_tokens=output_tokens,
        billing_total_tokens=total_tokens,
        estimated_input_tokens=estimated_input_tokens,
        estimated_input_tokenizer="o200k_base" if estimated_input_tokens is not None else None,
        estimated_input_model=model if estimated_input_tokens is not None else None,
    )
    session.add(record)
    return record
