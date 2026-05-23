from __future__ import annotations

from pathlib import Path

from llm_observe_proxy.config import ModelRoute, Settings
from llm_observe_proxy.database import (
    create_db_engine,
    create_session_factory,
    session_scope,
    set_default_model,
    set_default_provider_slug,
    set_fallback_enabled,
    upsert_model_provider,
    upsert_model_route_db,
)
from llm_observe_proxy.routing import (
    build_forward_body,
    select_model_route,
    simulate_route_resolution,
)


def test_exact_match_from_startup_config() -> None:
    settings = Settings(
        model_routes=(
            ModelRoute(model="local", upstream_url="http://localhost:8000/v1"),
        )
    )

    decision = select_model_route({"model": "local"}, settings)

    assert decision.model_route == "local"
    assert decision.match_source == "startup"
    assert decision.upstream_model == "local"


def test_prefix_match_and_priority(tmp_path: Path) -> None:
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_route_db(
            session,
            incoming_model="qwen-*",
            match_type="prefix",
            upstream_url="http://localhost:8000/v1",
            upstream_model="qwen-general",
            priority=50,
        )
        upsert_model_route_db(
            session,
            incoming_model="qwen-chat-*",
            match_type="prefix",
            upstream_url="http://localhost:8000/v1",
            upstream_model="qwen-chat",
            priority=50,
        )

        decision = select_model_route({"model": "qwen-chat-fast"}, settings, session=session)

    assert decision.model_route == "qwen-chat-*"
    assert decision.match_type == "prefix"
    assert decision.upstream_model == "qwen-chat"


def test_exact_beats_prefix_at_same_priority(tmp_path: Path) -> None:
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_route_db(
            session,
            incoming_model="gpt-*",
            match_type="prefix",
            upstream_url="http://localhost:8000/v1",
            upstream_model="prefix-model",
            priority=20,
        )
        upsert_model_route_db(
            session,
            incoming_model="gpt-4",
            match_type="exact",
            upstream_url="http://localhost:8000/v1",
            upstream_model="exact-model",
            priority=20,
        )

        decision = select_model_route({"model": "gpt-4"}, settings, session=session)

    assert decision.model_route == "gpt-4"
    assert decision.upstream_model == "exact-model"


def test_inactive_route_falls_to_fallback(tmp_path: Path) -> None:
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(
            session,
            slug="fallback",
            name="Fallback",
            upstream_url="http://fallback.test/v1",
        )
        set_default_provider_slug(session, "fallback")
        set_default_model(session, "fallback-model")
        upsert_model_route_db(
            session,
            incoming_model="local",
            match_type="exact",
            upstream_url="http://localhost:8000/v1",
            active=False,
        )

        decision = select_model_route({"model": "local"}, settings, session=session)

    assert decision.fallback_used is True
    assert decision.provider_slug == "fallback"
    assert decision.upstream_model == "fallback-model"


def test_fallback_disabled_returns_no_match(tmp_path: Path) -> None:
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        set_fallback_enabled(session, False)

        decision = select_model_route({"model": "missing"}, settings, session=session)

    assert decision.model_route is None
    assert decision.fallback_used is False


def test_route_simulator_reports_match_and_missing_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MISSING_ROUTE_KEY", raising=False)
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(
            session,
            slug="router",
            name="Router",
            upstream_url="http://router.test/v1",
        )
        upsert_model_route_db(
            session,
            incoming_model="qwen-*",
            match_type="prefix",
            upstream_url="http://router.test/v1",
            upstream_model="qwen",
            provider_slug="router",
            api_key_env="MISSING_ROUTE_KEY",
        )

        result = simulate_route_resolution("qwen-chat", session, settings)

    assert result.status == "missing_api_key"
    assert result.matched_route == "qwen-*"
    assert result.provider_name == "Router"


def test_forward_body_rewrites_fallback_model(tmp_path: Path) -> None:
    session_factory, settings = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(
            session,
            slug="fallback",
            name="Fallback",
            upstream_url="http://fallback.test/v1",
        )
        set_default_provider_slug(session, "fallback")
        set_default_model(session, "fallback-model")
        payload = {"model": "unknown", "messages": []}
        decision = select_model_route(payload, settings, session=session)

    body = build_forward_body(b'{"model":"unknown","messages":[]}', payload, decision)

    assert b"fallback-model" in body


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "routes.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    create_session_factory(engine)
    from llm_observe_proxy.database import init_db

    init_db(engine)
    return create_session_factory(engine), settings
