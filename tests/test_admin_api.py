from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from llm_observe_proxy.database import RequestRecord


def test_get_settings_summary(proxy_client: TestClient) -> None:
    response = proxy_client.get("/admin/api/settings/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["listener"]["port"] == 8080
    assert data["client_base_url"] == "http://localhost:8080/v1"
    assert "stored_rows" in data


def test_seeded_local_llm_provider_is_available_for_fallback(proxy_client: TestClient) -> None:
    providers = proxy_client.get("/admin/api/providers?search=local-llm")
    settings = proxy_client.post(
        "/admin/api/settings/upstream-defaults",
        json={
            "upstream_url": "http://localhost:8000/v1",
            "default_provider_slug": "local-llm",
            "default_model": "local-model",
            "fallback_enabled": True,
        },
    )

    assert providers.status_code == 200
    data = providers.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Local LLM"
    assert data["items"][0]["upstream_url"] == "http://localhost:8000/v1"
    assert data["items"][0]["api_key_env"] is None
    assert settings.status_code == 200
    assert settings.json()["upstream"]["default_provider_slug"] == "local-llm"


def test_update_upstream_defaults_valid(proxy_client: TestClient) -> None:
    provider_response = proxy_client.post(
        "/admin/api/providers",
        json={
            "slug": "local-test",
            "name": "Local Test",
            "upstream_url": "http://localhost:8002/v1",
            "active": True,
        },
    )
    assert provider_response.status_code == 200

    response = proxy_client.post(
        "/admin/api/settings/upstream-defaults",
        json={
            "upstream_url": "http://localhost:8000/v1",
            "default_provider_slug": "local-test",
            "default_model": "qwen-local",
            "fallback_enabled": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["upstream"]["default_provider_slug"] == "local-test"
    assert data["upstream"]["default_model"] == "qwen-local"


def test_provider_crud_and_filters(proxy_client: TestClient) -> None:
    created = proxy_client.post(
        "/admin/api/providers",
        json={
            "slug": "custom",
            "name": "Custom Provider",
            "upstream_url": "http://custom.test/v1",
            "currency": "EUR",
            "api_key_env": "CUSTOM_KEY",
            "capabilities": {"text": True},
        },
    )
    assert created.status_code == 200
    assert created.json()["api_key_env"] == "CUSTOM_KEY"

    listed = proxy_client.get("/admin/api/providers?search=custom&currency=EUR")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = proxy_client.put(
        "/admin/api/providers/custom",
        json={
            "name": "Updated Provider",
            "upstream_url": "http://custom.test/v1",
            "currency": "USD",
            "active": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    deleted = proxy_client.delete("/admin/api/providers/custom")
    assert deleted.status_code == 200


def test_route_crud_and_simulation(proxy_client: TestClient) -> None:
    proxy_client.post(
        "/admin/api/providers",
        json={
            "slug": "route-local",
            "name": "Route Local",
            "upstream_url": "http://localhost:8003/v1",
        },
    )
    route = proxy_client.post(
        "/admin/api/routes",
        json={
            "incoming_model": "qwen-*",
            "match_type": "prefix",
            "upstream_url": "http://localhost:8003/v1",
            "upstream_model": "qwen3",
            "provider_slug": "route-local",
            "priority": 25,
        },
    )
    assert route.status_code == 200
    route_id = route.json()["id"]

    listed = proxy_client.get("/admin/api/routes?search=qwen")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    simulated = proxy_client.post(
        "/admin/api/routes/simulate",
        json={"incoming_model": "qwen-chat", "message_type": "simple"},
    )
    assert simulated.status_code == 200
    assert simulated.json()["matched_route"] == "qwen-*"

    updated = proxy_client.put(
        f"/admin/api/routes/{route_id}",
        json={
            "incoming_model": "qwen-*",
            "match_type": "prefix",
            "upstream_url": "http://localhost:8003/v1",
            "upstream_model": "qwen3-updated",
            "provider_slug": "route-local",
            "active": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    deleted = proxy_client.delete(f"/admin/api/routes/{route_id}")
    assert deleted.status_code == 200


def test_retention_preview_and_trim(proxy_client: TestClient, proxy_app) -> None:
    with proxy_app.state.session_factory() as session:
        session.add(
            RequestRecord(
                created_at=datetime.now(UTC) - timedelta(days=90),
                method="POST",
                path="/v1/chat/completions",
                endpoint="/v1/chat/completions",
                upstream_url="http://localhost:8080/v1/chat/completions",
                request_headers_json="{}",
                request_body=b"{}",
            )
        )
        session.commit()

    preview = proxy_client.get("/admin/api/settings/retention-preview?days=30")
    assert preview.status_code == 200
    assert preview.json()["rows"] == 1

    rejected = proxy_client.post("/admin/api/settings/trim", json={"days": 30})
    assert rejected.status_code == 400

    trimmed = proxy_client.post("/admin/api/settings/trim", json={"days": 30, "confirm": True})
    assert trimmed.status_code == 200
    assert trimmed.json()["deleted"] == 1


def test_usage_endpoints(proxy_client: TestClient) -> None:
    assert proxy_client.get("/admin/api/providers/usage").status_code == 200
    assert proxy_client.get("/admin/api/routes/usage").status_code == 200


def test_live_run_rest_actions_and_missing_resources(proxy_client: TestClient) -> None:
    blank = proxy_client.post("/admin/api/runs/start", json={"name": "   "})
    assert blank.status_code == 400
    assert blank.json() == {"detail": "Run name is required."}

    started = proxy_client.post(
        "/admin/api/runs/start",
        json={"name": "REST benchmark", "notes": "live poll"},
    )
    assert started.status_code == 200
    assert started.json()["run"]["name"] == "REST benchmark"
    assert started.json()["run"]["is_active"] is True

    runs = proxy_client.get("/admin/api/runs")
    assert runs.status_code == 200
    assert runs.json()["active_run"]["name"] == "REST benchmark"

    detail = proxy_client.get("/admin/api/runs/1")
    assert detail.status_code == 200
    assert detail.json()["run"]["notes"] == "live poll"

    ended = proxy_client.post("/admin/api/runs/end")
    assert ended.status_code == 200
    assert ended.json()["run"]["is_active"] is False

    assert proxy_client.get("/admin/api/requests/999").status_code == 404
    assert proxy_client.get("/admin/api/runs/999").status_code == 404


def test_requests_api_uses_bounded_preview_and_detail_keeps_full_body(
    proxy_client: TestClient,
    proxy_app,
) -> None:
    large_response = "x" * (70 * 1024)
    with proxy_app.state.session_factory() as session:
        record = RequestRecord(
            completed_at=datetime.now(UTC),
            method="POST",
            path="/v1/chat/completions",
            endpoint="/v1/chat/completions",
            model="large-model",
            upstream_url="http://localhost:8080/v1/chat/completions",
            request_headers_json="{}",
            request_body=b"{}",
            response_status=200,
            response_headers_json="{}",
            response_body=large_response.encode(),
            response_content_type="text/plain",
            duration_ms=1000,
            billing_input_tokens=1,
            billing_output_tokens=2,
            billing_total_tokens=3,
        )
        session.add(record)
        session.commit()
        record_id = record.id

    listed = proxy_client.get("/admin/api/requests")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["id"] == record_id
    assert item["model"] == "large-model"
    assert item["preview"].endswith("...")
    assert len(item["preview"]) < 200
    assert item["tokens"]["input_display"] == "1"
    assert item["tokens"]["output_display"] == "2"
    assert item["tokens"]["total_display"] == "3"

    detail = proxy_client.get(f"/admin/api/requests/{record_id}?mode=text")
    assert detail.status_code == 200
    assert detail.json()["response_render"]["text"] == large_response
