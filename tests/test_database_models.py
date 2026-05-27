from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from llm_observe_proxy.config import ModelRoute, Settings
from llm_observe_proxy.database import (
    DEFAULT_ROUTE_SEED_OWNER,
    MODEL_ROUTES_SETTING_KEY,
    ModelProvider,
    apply_default_model_routes,
    create_db_engine,
    create_session_factory,
    get_default_fallback_provider,
    get_default_model,
    get_default_provider_slug,
    get_fallback_summary,
    get_ui_model_routes,
    init_db,
    is_fallback_enabled,
    list_active_model_providers,
    list_model_routes_db,
    preview_default_model_routes,
    session_scope,
    set_default_fallback_provider,
    set_default_model,
    set_default_provider_slug,
    set_setting,
    upsert_model_price,
    upsert_model_provider,
    upsert_model_route_db,
)


def test_upsert_provider_with_new_fields(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        provider = upsert_model_provider(
            session,
            slug="local",
            name="Local Provider",
            upstream_url="http://localhost:8004/v1",
            currency="local",
            api_key_env="LOCAL_KEY",
            active=False,
            capabilities={"text": True, "vision": False},
        )

        assert provider.api_key_env == "LOCAL_KEY"
        assert provider.active is False
        assert json.loads(provider.capabilities_json or "{}") == {
            "text": True,
            "vision": False,
        }


def test_set_default_fallback_provider_clears_others(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(session, slug="one", name="One", upstream_url="http://one.test/v1")
        upsert_model_provider(session, slug="two", name="Two", upstream_url="http://two.test/v1")

        set_default_fallback_provider(session, "one")
        set_default_fallback_provider(session, "two")

        assert get_default_fallback_provider(session).slug == "two"
        assert session.get(ModelProvider, "one").is_default_fallback is False


def test_list_active_providers_excludes_inactive(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(session, slug="active-one", name="Active")
        upsert_model_provider(session, slug="inactive-one", name="Inactive", active=False)

        slugs = {provider.slug for provider in list_active_model_providers(session)}

        assert "active-one" in slugs
        assert "inactive-one" not in slugs


def test_create_route_prefix_match_and_validation(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        route = upsert_model_route_db(
            session,
            incoming_model="qwen-*",
            match_type="prefix",
            upstream_url="http://localhost:8000/v1",
            upstream_model="qwen3-coder",
            compatibility_fixes=["qwen-tagged-tool-call-rewrite"],
            priority=25,
        )

        assert route.id is not None
        assert route.match_type == "prefix"
        assert route.priority == 25
        assert route.fixes == ("qwen-tagged-tool-call-rewrite",)


def test_init_db_seeds_default_routes_from_active_prices(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        route = next(
            route
            for route in list_model_routes_db(session)
            if route.incoming_model == "gpt-5.4-mini"
        )

        assert route.managed_by == DEFAULT_ROUTE_SEED_OWNER
        assert route.provider_slug == "openai"
        assert route.upstream_url == "https://api.openai.com/v1"
        assert route.effective_upstream_model == "gpt-5.4-mini"


def test_default_route_refresh_preserves_user_owned_route(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        route = next(
            route
            for route in list_model_routes_db(session)
            if route.incoming_model == "gpt-5.4-mini"
        )
        upsert_model_route_db(
            session,
            route_id=route.id,
            incoming_model="gpt-5.4-mini",
            match_type="exact",
            upstream_url="http://localhost:8000/v1",
            upstream_model="local-mini",
            provider_slug="local-llm",
            priority=25,
        )

        summary = apply_default_model_routes(
            session,
            provider_slug="openai",
            mode="refresh_seeded",
        )
        refreshed = next(
            route
            for route in list_model_routes_db(session)
            if route.incoming_model == "gpt-5.4-mini"
        )

        assert summary["skipped_user"] >= 1
        assert refreshed.managed_by is None
        assert refreshed.upstream_url == "http://localhost:8000/v1"
        assert refreshed.effective_upstream_model == "local-mini"


def test_default_route_builder_pins_lowest_cost_router_endpoint(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_price(
            session,
            provider_slug="openrouter",
            model="test/base",
            input_usd_per_million="1",
            output_usd_per_million="1",
        )
        upsert_model_price(
            session,
            provider_slug="openrouter",
            model="test/base@expensive",
            input_usd_per_million="2",
            output_usd_per_million="2",
        )
        upsert_model_price(
            session,
            provider_slug="openrouter",
            model="test/base@cheap",
            aliases="test-base-cheap",
            input_usd_per_million="0.1",
            cached_input_usd_per_million="0.01",
            output_usd_per_million="0.2",
        )

        preview = preview_default_model_routes(session, provider_slug="openrouter")
        summary = apply_default_model_routes(
            session,
            provider_slug="openrouter",
            mode="refresh_seeded",
        )
        routes = {route.incoming_model: route for route in list_model_routes_db(session)}

        assert preview["total_candidates"] >= 3
        assert summary["inserted"] >= 3
        assert routes["test/base"].effective_upstream_model == "test/base@cheap"
        assert routes["test/base@cheap"].effective_upstream_model == "test/base@cheap"
        assert routes["test/base:cheap"].effective_upstream_model == "test/base@cheap"
        assert routes["test-base-cheap"].effective_upstream_model == "test/base@cheap"


def test_duplicate_route_pattern_raises(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_route_db(
            session,
            incoming_model="qwen-*",
            match_type="prefix",
            upstream_url="http://localhost:8000/v1",
        )
        try:
            upsert_model_route_db(
                session,
                incoming_model="qwen-*",
                match_type="prefix",
                upstream_url="http://localhost:8000/v1",
            )
        except ValueError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("duplicate route did not raise")


def test_global_fallback_helpers(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_scope(session_factory) as session:
        upsert_model_provider(
            session,
            slug="fallback",
            name="Fallback",
            upstream_url="http://fallback.test/v1",
        )
        set_default_provider_slug(session, "fallback")
        set_default_model(session, "qwen-3")

        assert get_default_provider_slug(session) == "fallback"
        assert get_default_model(session) == "qwen-3"
        assert is_fallback_enabled(session) is True
        assert get_fallback_summary(session)["provider_name"] == "Fallback"


def test_migrate_json_blob_routes_to_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        set_setting(
            session,
            MODEL_ROUTES_SETTING_KEY,
            json.dumps(
                [
                    {
                        "model": "legacy",
                        "upstream_url": "http://localhost:8000/v1",
                        "upstream_model": "legacy-upstream",
                    }
                ]
            ),
        )
    engine.dispose()

    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        routes = list_model_routes_db(session)
        legacy_routes = [route for route in routes if route.incoming_model == "legacy"]
        assert len(legacy_routes) == 1
        assert legacy_routes[0].managed_by is None
        assert (
            ModelRoute(
                model="legacy",
                upstream_url="http://localhost:8000/v1",
                upstream_model="legacy-upstream",
            )
            in get_ui_model_routes(session)
        )


def test_provider_migration_adds_missing_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "old-provider.sqlite3"
    engine = create_db_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE model_providers ("
                "slug VARCHAR(64) PRIMARY KEY, name VARCHAR(128), "
                "upstream_url TEXT UNIQUE, currency VARCHAR(16), "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
    init_db(engine)
    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(model_providers)")).all()
        }
    assert {"api_key_env", "active", "is_default_fallback", "capabilities_json"} <= columns


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "models.sqlite3"
    engine = create_db_engine(f"sqlite:///{db_path.as_posix()}")
    init_db(engine)
    return create_session_factory(engine)
