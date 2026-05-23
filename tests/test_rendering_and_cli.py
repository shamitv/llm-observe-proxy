from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from llm_observe_proxy import create_app
from llm_observe_proxy.admin import _stream_token_usage
from llm_observe_proxy.capture import ExtractedTokenUsage, extract_token_usage, has_tool_payload
from llm_observe_proxy.cli import resolve_bind, run_historical_cached_cost_backfill
from llm_observe_proxy.config import (
    DEFAULT_INCOMING_HOST,
    DEFAULT_INCOMING_PORT,
    DEFAULT_UPSTREAM_URL,
    EXPOSED_INCOMING_HOST,
    Settings,
)
from llm_observe_proxy.costing import (
    HISTORICAL_CACHED_COST_BACKFILL,
    estimate_cost,
    estimate_run_cost,
)
from llm_observe_proxy.database import (
    ModelPrice,
    ModelPriceTier,
    ModelProvider,
    RequestRecord,
    create_db_engine,
    create_session_factory,
    delete_model_price_tier,
    init_db,
    session_scope,
    set_incoming_server,
    upsert_model_price,
    upsert_model_price_tier,
)
from llm_observe_proxy.rendering import render_payload
from llm_observe_proxy.token_estimation import estimate_input_tokens

FIXTURES = Path(__file__).parent / "fixtures" / "usage_shapes"


def _load_fixture_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


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


def test_renderer_text_mode_does_not_parse_sse_events(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("text mode should not parse SSE events")

    monkeypatch.setattr("llm_observe_proxy.rendering.decode_sse_json_events", fail_decode)

    rendered = render_payload(
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
        "text/event-stream",
        "text",
    )

    assert rendered.mode == "text"
    assert "data:" in rendered.text


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


def test_extract_token_usage_supports_chat_responses_and_responses_api() -> None:
    chat_usage = extract_token_usage(
        {
            "usage": {
                "prompt_tokens": 6,
                "completion_tokens": 3,
                "total_tokens": 9,
                "prompt_tokens_details": {"cached_tokens": 4},
            }
        }
    )
    assert chat_usage.input_tokens == 6
    assert chat_usage.cached_input_tokens == 4
    assert chat_usage.output_tokens == 3
    assert chat_usage.total_tokens == 9

    responses_usage = extract_token_usage(
        [
            {
                "response": {
                    "usage": {
                        "input_tokens": 8,
                        "output_tokens": 4,
                        "input_tokens_details": {"cache_read_tokens": 3},
                    }
                }
            }
        ]
    )
    assert responses_usage.input_tokens == 8
    assert responses_usage.cached_input_tokens == 3
    assert responses_usage.output_tokens == 4
    assert responses_usage.total_tokens == 12

    input_cached_usage = extract_token_usage(
        {
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 7},
            }
        }
    )
    assert input_cached_usage.input_tokens == 20
    assert input_cached_usage.cached_input_tokens == 7
    assert input_cached_usage.output_tokens == 5
    assert input_cached_usage.total_tokens == 25


def test_extract_token_usage_supports_live_provider_fixtures() -> None:
    openai_chat = extract_token_usage(_load_fixture_json("openai_chat_completion.json"))
    assert openai_chat.input_tokens == 12
    assert openai_chat.cached_input_tokens == 4
    assert openai_chat.output_tokens == 1
    assert openai_chat.total_tokens == 13

    openai_responses = extract_token_usage(_load_fixture_json("openai_responses.json"))
    assert openai_responses.input_tokens == 12
    assert openai_responses.cached_input_tokens == 5
    assert openai_responses.output_tokens == 2
    assert openai_responses.total_tokens == 14

    hf_router = extract_token_usage(_load_fixture_json("hf_router_chat_completion.json"))
    assert hf_router.input_tokens == 40
    assert hf_router.cached_input_tokens == 6
    assert hf_router.output_tokens == 2
    assert hf_router.total_tokens == 42

    openrouter = extract_token_usage(_load_fixture_json("openrouter_chat_completion.json"))
    assert openrouter.input_tokens == 15
    assert openrouter.cached_input_tokens == 3
    assert openrouter.cache_write_input_tokens == 7
    assert openrouter.output_tokens == 2
    assert openrouter.total_tokens == 17


def test_extract_token_usage_supports_deepseek_cache_counters() -> None:
    usage = extract_token_usage(
        {
            "usage": {
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 10,
                "completion_tokens": 25,
            }
        }
    )

    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 90
    assert usage.output_tokens == 25
    assert usage.total_tokens == 125

    explicit_prompt_total = extract_token_usage(
        {
            "usage": {
                "prompt_tokens": 150,
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 10,
                "completion_tokens": 25,
            }
        }
    )

    assert explicit_prompt_total.input_tokens == 150
    assert explicit_prompt_total.cached_input_tokens == 90
    assert explicit_prompt_total.output_tokens == 25


def test_extract_token_usage_prefers_openai_usage_over_provider_fallbacks() -> None:
    usage = extract_token_usage(
        {
            "usage": {
                "prompt_tokens": 6,
                "completion_tokens": 3,
                "total_tokens": 9,
            },
            "timings": {"cache_n": 15, "prompt_n": 1185, "predicted_n": 40},
        }
    )

    assert usage.input_tokens == 6
    assert usage.cached_input_tokens is None
    assert usage.output_tokens == 3
    assert usage.total_tokens == 9


def test_extract_token_usage_supports_provider_fallback_shapes() -> None:
    timings_usage = extract_token_usage(
        {
            "choices": [{"finish_reason": "stop", "index": 0, "delta": {}}],
            "timings": {"cache_n": 15, "prompt_n": 1185, "predicted_n": 40},
        }
    )
    assert timings_usage.input_tokens == 1200
    assert timings_usage.cached_input_tokens == 15
    assert timings_usage.output_tokens == 40
    assert timings_usage.total_tokens == 1240

    ollama_usage = extract_token_usage(
        {
            "model": "llama3.2",
            "done": True,
            "prompt_eval_count": 11,
            "eval_count": 18,
        }
    )
    assert ollama_usage.input_tokens == 11
    assert ollama_usage.cached_input_tokens is None
    assert ollama_usage.output_tokens == 18
    assert ollama_usage.total_tokens == 29


def test_extract_token_usage_handles_partial_provider_metrics() -> None:
    partial_usage = extract_token_usage(
        {
            "prompt_eval_count": 11,
            "eval_count": "not-counted",
        }
    )
    malformed_usage = extract_token_usage(
        {
            "timings": {"prompt_n": False, "predicted_n": "40"},
        }
    )

    assert partial_usage.input_tokens == 11
    assert partial_usage.output_tokens is None
    assert partial_usage.total_tokens is None
    assert malformed_usage.input_tokens is None
    assert malformed_usage.output_tokens is None
    assert malformed_usage.total_tokens is None


def test_stream_token_usage_reads_final_sse_usage_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("stream usage should use targeted final-event parsing")

    monkeypatch.setattr("llm_observe_proxy.capture.decode_sse_json_events", fail_decode)
    body = b"".join(
        [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":1000,'
            b'"completion_tokens":25,"total_tokens":1025,'
            b'"prompt_tokens_details":{"cached_tokens":900}}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    usage = _stream_token_usage(body)

    assert usage.input_tokens == 1000
    assert usage.cached_input_tokens == 900
    assert usage.output_tokens == 25
    assert usage.total_tokens == 1025


def test_stream_token_usage_reads_fixture_usage_events() -> None:
    openai_usage = _stream_token_usage(_load_fixture_bytes("openai_chat_stream.sse"))
    assert openai_usage.input_tokens == 12
    assert openai_usage.cached_input_tokens == 4
    assert openai_usage.output_tokens == 1
    assert openai_usage.total_tokens == 13

    openrouter_usage = _stream_token_usage(_load_fixture_bytes("openrouter_chat_stream.sse"))
    assert openrouter_usage.input_tokens == 15
    assert openrouter_usage.cached_input_tokens == 3
    assert openrouter_usage.cache_write_input_tokens == 7
    assert openrouter_usage.output_tokens == 2
    assert openrouter_usage.total_tokens == 17


def test_stream_token_usage_reads_final_sse_timings_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("stream timings should use targeted final-event parsing")

    monkeypatch.setattr("llm_observe_proxy.capture.decode_sse_json_events", fail_decode)
    body = b"".join(
        [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"stop","index":0,"delta":{}}],'
            b'"timings":{"cache_n":0,"prompt_n":1185,"predicted_n":40}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    usage = _stream_token_usage(body)

    assert usage.input_tokens == 1185
    assert usage.cached_input_tokens == 0
    assert usage.output_tokens == 40
    assert usage.total_tokens == 1225


def test_stream_token_usage_reads_final_sse_ollama_metric_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_decode(_body: bytes | None):
        raise AssertionError("stream metrics should use targeted final-event parsing")

    monkeypatch.setattr("llm_observe_proxy.capture.decode_sse_json_events", fail_decode)
    body = b"".join(
        [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
            b'data: {"done":true,"prompt_eval_count":11,"eval_count":18}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    usage = _stream_token_usage(body)

    assert usage.input_tokens == 11
    assert usage.output_tokens == 18
    assert usage.total_tokens == 29


def test_tool_detector_ignores_non_string_type_fields() -> None:
    payload = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {"type": {"type": "string"}},
                    },
                },
            }
        ]
    }

    assert has_tool_payload(payload) is True


def test_estimate_input_tokens_supports_openai_request_shapes() -> None:
    chat_estimate = estimate_input_tokens(
        {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello world"}],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
        },
        endpoint="/v1/chat/completions",
        model="gpt-test",
    )
    responses_estimate = estimate_input_tokens(
        {"input": "summarize this", "tools": [{"type": "web_search_preview"}]},
        endpoint="/v1/responses",
        model=None,
    )
    unknown = estimate_input_tokens({"temperature": 0}, endpoint="/v1/models", model=None)

    assert chat_estimate is not None
    assert chat_estimate.tokens > 0
    assert chat_estimate.model == "gpt-test"
    assert responses_estimate is not None
    assert responses_estimate.tokens > 0
    assert responses_estimate.tokenizer == "o200k_base"
    assert unknown is None


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
    assert "--models-file" in completed.stdout
    assert "--backfill-cached-costs" in completed.stdout
    assert DEFAULT_INCOMING_HOST == "localhost"
    assert DEFAULT_INCOMING_PORT == 8080
    assert DEFAULT_UPSTREAM_URL == "http://localhost:8000/v1"


def test_module_cli_backfill_cached_costs_exits(tmp_path) -> None:
    db_path = tmp_path / "backfill-cli.sqlite3"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "llm_observe_proxy",
            "--database-url",
            f"sqlite:///{db_path.as_posix()}",
            "--backfill-cached-costs",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Historical cached-cost backfill updated 0 request record(s)." in completed.stdout


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


def test_init_db_seeds_model_pricing_without_overwriting_edits(tmp_path) -> None:
    db_path = tmp_path / "pricing.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)

    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        providers = session.scalars(select(ModelProvider.slug).order_by(ModelProvider.slug)).all()
        openai_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.4-mini",
            )
        ).one()
        assert openai_price.cached_input_usd_per_million == Decimal("0.075000")
        assert openai_price.checked_at == "2026-05-23"
        openai_price.input_usd_per_million = Decimal("123")
        qwen_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "alibaba",
                ModelPrice.model == "qwen3-coder-plus",
            )
        ).one()
        openrouter_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openrouter",
                ModelPrice.model == "openai/gpt-oss-120b",
            )
        ).one()
        openrouter_price.input_usd_per_million = Decimal("999")

        assert qwen_price.source_url == (
            "https://www.alibabacloud.com/help/en/model-studio/model-pricing"
        )
        assert qwen_price.checked_at == "2026-05-23"
        assert qwen_price.release_date == "2025-09-23"
        assert "qwen/qwen3-coder-plus" in json.loads(qwen_price.aliases_json)
        assert len(qwen_price.tiers) == 4
        assert qwen_price.tiers[0].cached_input_usd_per_million == Decimal("0.114800")

        deepseek_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "deepseek",
                ModelPrice.model == "deepseek-v4-flash",
            )
        ).one()
        assert deepseek_price.cached_input_usd_per_million == Decimal("0.002800")

        hf_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "huggingface-router",
                ModelPrice.model == "openai/gpt-oss-120b",
            )
        ).one()
        assert hf_price.output_usd_per_million == Decimal("0.250000")

        anthropic_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "anthropic",
                ModelPrice.model == "claude-sonnet-4-6",
            )
        ).one()
        assert anthropic_price.cached_input_usd_per_million == Decimal("0.300000")

        google_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "google",
                ModelPrice.model == "gemini-2.5-pro",
            )
        ).one()
        assert google_price.cached_input_usd_per_million == Decimal("0.125000")
        assert len(google_price.tiers) == 2

        new_google_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "google",
                ModelPrice.model == "gemini-3.5-flash",
            )
        ).one()
        assert new_google_price.source_url == "https://ai.google.dev/gemini-api/docs/pricing"
        assert "google/gemini-3.5-flash" in json.loads(new_google_price.aliases_json)

        new_alibaba_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "alibaba",
                ModelPrice.model == "qwen3-coder-30b-a3b-instruct",
            )
        ).one()
        assert new_alibaba_price.source_url == (
            "https://www.alibabacloud.com/help/en/model-studio/model-pricing"
        )
        assert "Qwen/Qwen3-Coder-30B-A3B-Instruct" in json.loads(
            new_alibaba_price.aliases_json
        )

        zai_successor_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "zai",
                ModelPrice.model == "glm-4.7",
            )
        ).one()
        assert zai_successor_price.cached_input_usd_per_million == Decimal("0.110000")

        mistral_successor_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "mistral",
                ModelPrice.model == "mistral-medium-2604",
            )
        ).one()
        assert mistral_successor_price.cached_input_usd_per_million == Decimal("0.150000")

    init_db(engine)

    with session_scope(session_factory) as session:
        edited_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.4-mini",
            )
        ).one()
        edited_openrouter_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openrouter",
                ModelPrice.model == "openai/gpt-oss-120b",
            )
        ).one()
        price_count = session.scalar(text("SELECT count(*) FROM model_prices"))
    engine.dispose()

    assert {"alibaba", "deepseek", "huggingface-router", "moonshot", "openrouter"} <= set(
        providers
    )
    assert edited_price.input_usd_per_million == Decimal("123.000000")
    assert edited_openrouter_price.input_usd_per_million == Decimal("999.000000")
    assert price_count >= 51


def test_init_db_refreshes_only_seed_owned_model_pricing_rows(tmp_path) -> None:
    db_path = tmp_path / "pricing-refresh.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    legacy_models = [
        ("openai", "gpt-5.4-mini", "GPT-5.4 Mini", "0.75", "4.50"),
        ("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6", "3.00", "15.00"),
        ("google", "gemini-2.5-pro", "Gemini 2.5 Pro", "1.25", "10.00"),
    ]
    with session_scope(session_factory) as session:
        for provider_slug, model, display_name, input_rate, output_rate in legacy_models:
            price = session.scalars(
                select(ModelPrice).where(
                    ModelPrice.provider_slug == provider_slug,
                    ModelPrice.model == model,
                )
            ).one()
            price.display_name = display_name
            price.aliases_json = None
            price.input_usd_per_million = Decimal(input_rate)
            price.cached_input_usd_per_million = None
            price.output_usd_per_million = Decimal(output_rate)
            price.active = True
            price.source_url = None
            price.checked_at = None
            price.release_date = None
            price.notes = "Legacy scalar seed from v0.3."
            price.tiers.clear()

        edited_price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.5",
            )
        ).one()
        edited_price.cached_input_usd_per_million = None
        edited_price.source_url = None
        edited_price.checked_at = None
        edited_price.release_date = None
        edited_price.notes = "Legacy scalar seed from v0.3."
        edited_price.input_usd_per_million = Decimal("123")

    init_db(engine)

    with session_scope(session_factory) as session:
        refreshed_openai = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.4-mini",
            )
        ).one()
        refreshed_anthropic = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "anthropic",
                ModelPrice.model == "claude-sonnet-4-6",
            )
        ).one()
        refreshed_google = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "google",
                ModelPrice.model == "gemini-2.5-pro",
            )
        ).one()
        preserved_edit = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.5",
            )
        ).one()
        refreshed_google_tier_count = len(refreshed_google.tiers)
        refreshed_google_high_tier_min = refreshed_google.tiers[1].min_input_tokens
        refreshed_google_high_tier_cached = refreshed_google.tiers[
            1
        ].cached_input_usd_per_million
    engine.dispose()

    assert refreshed_openai.cached_input_usd_per_million == Decimal("0.075000")
    assert refreshed_openai.source_url == "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
    assert refreshed_anthropic.cached_input_usd_per_million == Decimal("0.300000")
    assert refreshed_anthropic.source_url == "https://platform.claude.com/docs/en/about-claude/pricing"
    assert refreshed_google.cached_input_usd_per_million == Decimal("0.125000")
    assert refreshed_google_tier_count == 2
    assert refreshed_google_high_tier_min == 200001
    assert refreshed_google_high_tier_cached == Decimal("0.250000")
    assert preserved_edit.input_usd_per_million == Decimal("123.000000")
    assert preserved_edit.cached_input_usd_per_million is None
    assert preserved_edit.source_url is None


def test_manual_backfill_reprices_historical_cached_token_costs(tmp_path) -> None:
    db_path = tmp_path / "historical-cached-cost.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        session.add(ModelProvider(slug="local-null-url", name="Local Null URL"))
        upsert_model_price(
            session,
            provider_slug="openai",
            model="historical-cached-model",
            input_usd_per_million="1",
            cached_input_usd_per_million="0.1",
            output_usd_per_million="2",
        )
        session.add(
            RequestRecord(
                method="POST",
                path="/v1/chat/completions",
                endpoint="/v1/chat/completions",
                model="historical-cached-model",
                upstream_url="https://api.openai.com/v1/chat/completions",
                request_headers_json="{}",
                request_body=b'{"model":"historical-cached-model"}',
                response_body=json.dumps(
                    {
                        "model": "historical-cached-model",
                        "usage": {
                            "prompt_tokens": 1000,
                            "completion_tokens": 25,
                            "total_tokens": 1025,
                            "prompt_tokens_details": {"cached_tokens": 800},
                        },
                    }
                ).encode(),
                response_status=200,
                billing_input_tokens=1000,
                billing_cached_input_tokens=800,
                billing_output_tokens=25,
                billing_total_tokens=1025,
                billing_input_cost_usd=Decimal("0.00100000"),
                billing_output_cost_usd=Decimal("0.00005000"),
                billing_total_cost_usd=Decimal("0.00105000"),
                pricing_snapshot_json=json.dumps(
                    {
                        "provider_slug": "openai",
                        "billing_model": "historical-cached-model",
                    }
                ),
            )
        )
        session.add(
            RequestRecord(
                method="POST",
                path="/v1/chat/completions",
                endpoint="/v1/chat/completions",
                model="historical-cached-model",
                upstream_url="https://api.openai.com/v1/chat/completions",
                request_headers_json="{}",
                request_body=b'{"model":"historical-cached-model"}',
                response_body=json.dumps(
                    {
                        "model": "historical-cached-model",
                        "usage": {
                            "prompt_tokens": 1000,
                            "completion_tokens": 25,
                            "total_tokens": 1025,
                            "prompt_tokens_details": {"cached_tokens": 800},
                        },
                    }
                ).encode(),
                response_status=200,
                billing_total_cost_usd=Decimal("0.00105000"),
                pricing_snapshot_json=json.dumps(
                    {
                        "provider_slug": "openai",
                        "billing_model": "historical-cached-model",
                    }
                ),
            )
        )
        session.add(
            RequestRecord(
                method="POST",
                path="/v1/chat/completions",
                endpoint="/v1/chat/completions",
                model="historical-cached-model",
                upstream_url="https://api.openai.com/v1/chat/completions",
                request_headers_json="{}",
                request_body=b'{"model":"historical-cached-model"}',
                response_body=json.dumps(
                    {
                        "model": "historical-cached-model",
                        "usage": {
                            "prompt_tokens": 1000,
                            "completion_tokens": 25,
                            "total_tokens": 1025,
                            "prompt_tokens_details": {"cached_tokens": 800},
                        },
                    }
                ).encode(),
                response_status=200,
                billing_input_tokens=1000,
                billing_cached_input_tokens=800,
                billing_output_tokens=25,
                billing_total_tokens=1025,
                billing_input_cost_usd=Decimal("0.00028000"),
                billing_output_cost_usd=Decimal("0.00005000"),
                billing_total_cost_usd=Decimal("0.00033000"),
                pricing_snapshot_json=json.dumps(
                    {
                        "provider_slug": "openai",
                        "billing_model": "historical-cached-model",
                        "cached_input_pricing": "cached_input_rate",
                    }
                ),
            )
        )
        session.add(
            RequestRecord(
                method="POST",
                path="/v1/chat/completions",
                endpoint="/v1/chat/completions",
                upstream_url="https://api.openai.com/v1/chat/completions",
                request_headers_json="{}",
                request_body=b'{"model":"historical-cached-model","stream":true}',
                response_body=(
                    b'data: {"model":"historical-cached-model","usage":'
                    b'{"prompt_tokens":1000,"completion_tokens":25,'
                    b'"total_tokens":1025,"prompt_tokens_details":'
                    b'{"cached_tokens":800}}}\n\n'
                ),
                response_status=200,
                is_stream=True,
                billing_total_cost_usd=Decimal("0.00105000"),
                pricing_snapshot_json=json.dumps(
                    {
                        "provider_slug": "openai",
                        "billing_model": "historical-cached-model",
                    }
                ),
            )
        )

    assert run_historical_cached_cost_backfill(settings) == 3

    with session_scope(session_factory) as session:
        rows = session.scalars(select(RequestRecord).order_by(RequestRecord.id)).all()
        snapshots = [json.loads(row.pricing_snapshot_json or "{}") for row in rows]
    engine.dispose()

    assert [row.billing_total_cost_usd for row in rows] == [
        Decimal("0.00033000"),
        Decimal("0.00033000"),
        Decimal("0.00033000"),
        Decimal("0.00033000"),
    ]
    assert [row.billing_cached_input_tokens for row in rows] == [800, 800, 800, 800]
    assert snapshots[0]["cached_input_pricing"] == "cached_input_rate"
    assert snapshots[0]["historical_cost_backfill"] == HISTORICAL_CACHED_COST_BACKFILL
    assert snapshots[0]["previous_total_cost_usd"] == "0.00105000"
    assert snapshots[1]["historical_cost_backfill"] == HISTORICAL_CACHED_COST_BACKFILL
    assert snapshots[2].get("historical_cost_backfill") is None
    assert snapshots[3]["historical_cost_backfill"] == HISTORICAL_CACHED_COST_BACKFILL


def test_model_price_tiers_validate_bounds_and_preserve_relationships(tmp_path) -> None:
    db_path = tmp_path / "tiered-pricing.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        price = upsert_model_price(
            session,
            provider_slug="openai",
            model="tiered-model",
            display_name="Tiered Model",
            input_usd_per_million="1",
            cached_input_usd_per_million="0.1",
            output_usd_per_million="2",
            source_url="https://example.com/pricing",
            checked_at="2026-05-23",
            release_date="2026-01-15",
            notes="source metadata",
        )
        low = upsert_model_price_tier(
            session,
            model_price_id=price.id,
            min_input_tokens="",
            max_input_tokens="1000",
            input_usd_per_million="0.5",
            cached_input_usd_per_million="0.05",
            output_usd_per_million="1",
            label="short",
            source_url="https://example.com/tier",
            checked_at="2026-05-23",
            release_date="2026-01-15",
        )
        high = upsert_model_price_tier(
            session,
            model_price_id=price.id,
            min_input_tokens="1000",
            max_input_tokens="",
            input_usd_per_million="1",
            output_usd_per_million="2",
            label="long",
        )

        with pytest.raises(ValueError, match="overlaps"):
            upsert_model_price_tier(
                session,
                model_price_id=price.id,
                min_input_tokens="999",
                max_input_tokens="2000",
                input_usd_per_million="1",
                output_usd_per_million="2",
            )
        with pytest.raises(ValueError, match="greater than"):
            upsert_model_price_tier(
                session,
                model_price_id=price.id,
                min_input_tokens="10",
                max_input_tokens="10",
                input_usd_per_million="1",
                output_usd_per_million="2",
            )
        with pytest.raises(ValueError, match="greater than"):
            upsert_model_price_tier(
                session,
                model_price_id=price.id,
                min_input_tokens="",
                max_input_tokens="0",
                input_usd_per_million="1",
                output_usd_per_million="2",
            )

        assert price.source_url == "https://example.com/pricing"
        assert price.checked_at == "2026-05-23"
        assert price.release_date == "2026-01-15"
        assert low.min_input_tokens is None
        assert low.max_input_tokens == 1000
        assert low.cached_input_usd_per_million == Decimal("0.050000")
        assert high.max_input_tokens is None
        assert delete_model_price_tier(session, low.id) is True
        assert delete_model_price_tier(session, low.id) is False
        session.flush()
        assert session.get(ModelPriceTier, low.id) is None

        price_id = price.id
        session.delete(price)
        session.flush()
        assert session.scalars(
            select(ModelPriceTier).where(ModelPriceTier.model_price_id == price_id)
        ).all() == []
    engine.dispose()


def test_init_db_upgrades_existing_sqlite_model_prices_with_source_and_tiers(
    tmp_path,
) -> None:
    db_path = tmp_path / "old-pricing.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE model_providers ("
                "slug VARCHAR(64) PRIMARY KEY, "
                "name VARCHAR(128), "
                "upstream_url TEXT, "
                "currency VARCHAR(16), "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE model_prices ("
                "id INTEGER PRIMARY KEY, "
                "provider_slug VARCHAR(64), "
                "model VARCHAR(256), "
                "aliases_json TEXT, "
                "display_name VARCHAR(256), "
                "input_usd_per_million NUMERIC, "
                "output_usd_per_million NUMERIC, "
                "active BOOLEAN, "
                "notes TEXT, "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_providers "
                "(slug, name, upstream_url, currency) "
                "VALUES ('legacy', 'Legacy', 'http://localhost:9000/v1', 'USD')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_prices "
                "(id, provider_slug, model, input_usd_per_million, "
                "output_usd_per_million, active) "
                "VALUES (1, 'legacy', 'legacy-model', 1, 2, 1)"
            )
        )

    init_db(engine)

    inspector = inspect(engine)
    price_columns = {column["name"] for column in inspector.get_columns("model_prices")}
    tier_columns = {column["name"] for column in inspector.get_columns("model_price_tiers")}
    tier_indexes = {index["name"] for index in inspector.get_indexes("model_price_tiers")}
    with engine.connect() as connection:
        legacy_model = connection.execute(
            text("SELECT model FROM model_prices WHERE provider_slug = 'legacy'")
        ).scalar_one()
    engine.dispose()

    assert {"source_url", "checked_at", "release_date"}.issubset(price_columns)
    assert {
        "model_price_id",
        "min_input_tokens",
        "max_input_tokens",
        "cached_input_usd_per_million",
        "source_url",
        "checked_at",
        "release_date",
    }.issubset(tier_columns)
    assert "ix_model_price_tiers_model_price_id" in tier_indexes
    assert legacy_model == "legacy-model"


def test_cost_estimator_handles_rates_aliases_unknowns_and_missing_usage(tmp_path) -> None:
    db_path = tmp_path / "estimator.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        known = estimate_cost(
            session,
            usage=ExtractedTokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500),
            billing_model="gpt-5.4-mini",
            provider_slug="openai",
        )
        upsert_model_price(
            session,
            provider_slug="openai",
            model="alias-root",
            aliases="alias-one",
            input_usd_per_million="1",
            output_usd_per_million="2",
        )
        aliased = estimate_cost(
            session,
            usage=ExtractedTokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500),
            billing_model="alias-one",
            provider_slug="openai",
        )
        unknown = estimate_cost(
            session,
            usage=ExtractedTokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500),
            billing_model="missing-model",
            provider_slug="openai",
        )
        missing_usage = estimate_cost(
            session,
            usage=ExtractedTokenUsage(input_tokens=1000, output_tokens=None, total_tokens=None),
            billing_model="gpt-5.4-mini",
            provider_slug="openai",
        )
        cached = upsert_model_price(
            session,
            provider_slug="openai",
            model="cached-model",
            input_usd_per_million="1",
            cached_input_usd_per_million="0.1",
            output_usd_per_million="2",
        )
        cached_estimate = estimate_cost(
            session,
            usage=ExtractedTokenUsage(
                input_tokens=1000,
                cached_input_tokens=800,
                output_tokens=500,
                total_tokens=1500,
            ),
            billing_model=cached.model,
            provider_slug="openai",
        )
        cached_fallback = estimate_cost(
            session,
            usage=ExtractedTokenUsage(
                input_tokens=1000,
                cached_input_tokens=800,
                output_tokens=500,
                total_tokens=1500,
            ),
            billing_model="gpt-5.4-mini",
            provider_slug="openai",
        )
    engine.dispose()

    assert known.total_cost_usd == Decimal("0.003000")
    assert aliased.total_cost_usd == Decimal("0.002")
    assert aliased.snapshot["matched_model"] == "alias-root"
    assert unknown.total_cost_usd is None
    assert missing_usage.total_cost_usd is None
    assert cached_estimate.input_cost_usd == Decimal("0.00028")
    assert cached_estimate.cached_input_cost_usd == Decimal("0.00008")
    assert cached_estimate.total_cost_usd == Decimal("0.00128")
    assert cached_estimate.snapshot["cached_input_pricing"] == "cached_input_rate"
    assert cached_fallback.input_cost_usd == Decimal("0.000210")
    assert cached_fallback.cached_input_cost_usd == Decimal("0.000060")
    assert cached_fallback.snapshot["cached_input_pricing"] == "cached_input_rate"


def test_cost_estimator_uses_matching_model_price_tier_per_request(tmp_path) -> None:
    db_path = tmp_path / "tier-estimator.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        price = upsert_model_price(
            session,
            provider_slug="openai",
            model="tiered-cost-model",
            input_usd_per_million="10",
            cached_input_usd_per_million="1",
            output_usd_per_million="20",
            source_url="https://example.com/scalar",
            checked_at="2026-05-23",
        )
        low = upsert_model_price_tier(
            session,
            model_price_id=price.id,
            max_input_tokens="1000",
            input_usd_per_million="1",
            cached_input_usd_per_million="0.1",
            output_usd_per_million="2",
            label="short",
            source_url="https://example.com/short",
            checked_at="2026-05-23",
            notes="short tier",
        )
        high = upsert_model_price_tier(
            session,
            model_price_id=price.id,
            min_input_tokens="1000",
            input_usd_per_million="3",
            cached_input_usd_per_million="0.3",
            output_usd_per_million="6",
            label="long",
        )

        low_estimate = estimate_cost(
            session,
            usage=ExtractedTokenUsage(
                input_tokens=999,
                cached_input_tokens=900,
                cache_write_input_tokens=25,
                output_tokens=100,
                total_tokens=1099,
            ),
            billing_model=price.model,
            provider_slug="openai",
        )
        boundary_estimate = estimate_cost(
            session,
            usage=ExtractedTokenUsage(input_tokens=1000, output_tokens=100),
            billing_model=price.model,
            provider_slug="openai",
        )
        run_estimate = estimate_run_cost(
            [
                ExtractedTokenUsage(
                    input_tokens=999,
                    cached_input_tokens=900,
                    cache_write_input_tokens=25,
                    output_tokens=100,
                ),
                ExtractedTokenUsage(input_tokens=1000, output_tokens=100),
            ],
            price,
        )
    engine.dispose()

    assert low_estimate.input_cost_usd == Decimal("0.000189")
    assert low_estimate.output_cost_usd == Decimal("0.0002")
    assert low_estimate.total_cost_usd == Decimal("0.000389")
    assert low_estimate.cached_input_cost_usd == Decimal("0.00009")
    assert low_estimate.snapshot["pricing_source_kind"] == "model_price_tier"
    assert low_estimate.snapshot["tier_id"] == low.id
    assert low_estimate.snapshot["tier_label"] == "short"
    assert low_estimate.snapshot["source_url"] == "https://example.com/short"
    assert low_estimate.snapshot["cache_write_input_tokens"] == 25
    assert boundary_estimate.snapshot["tier_id"] == high.id
    assert boundary_estimate.input_cost_usd == Decimal("0.003")
    assert boundary_estimate.output_cost_usd == Decimal("0.0006")
    assert run_estimate.input_cost_usd == Decimal("0.003189")
    assert run_estimate.output_cost_usd == Decimal("0.0008")
    assert run_estimate.total_cost_usd == Decimal("0.003989")
    assert run_estimate.cached_input_cost_usd == Decimal("0.00009")
    assert run_estimate.cache_write_input_tokens == 25
    assert run_estimate.mixed_tiers is True


def test_run_cost_estimator_sums_usage_and_counts_missing_requests(tmp_path) -> None:
    db_path = tmp_path / "run-estimator.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "openai",
                ModelPrice.model == "gpt-5.4-mini",
            )
        ).one()
        estimate = estimate_run_cost(
            [
                ExtractedTokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500),
                ExtractedTokenUsage(input_tokens=None, output_tokens=10, total_tokens=None),
                ExtractedTokenUsage(
                    input_tokens=200,
                    cached_input_tokens=50,
                    output_tokens=100,
                    total_tokens=None,
                ),
            ],
            price,
        )
    engine.dispose()

    assert estimate.input_tokens == 1200
    assert estimate.cached_input_tokens == 50
    assert estimate.output_tokens == 600
    assert estimate.total_tokens == 1800
    assert estimate.input_cost_usd == Decimal("0.00086625")
    assert estimate.cached_input_cost_usd == Decimal("0.00000375")
    assert estimate.output_cost_usd == Decimal("0.002700")
    assert estimate.total_cost_usd == Decimal("0.00356625")
    assert estimate.included_request_count == 2
    assert estimate.missing_usage_request_count == 1


def test_seeded_google_tiers_apply_prompt_size_thresholds(tmp_path) -> None:
    db_path = tmp_path / "google-tier-estimator.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        price = session.scalars(
            select(ModelPrice).where(
                ModelPrice.provider_slug == "google",
                ModelPrice.model == "gemini-2.5-pro",
            )
        ).one()
        short_estimate = estimate_run_cost(
            [
                ExtractedTokenUsage(
                    input_tokens=200000,
                    cached_input_tokens=100000,
                    output_tokens=1000,
                    total_tokens=201000,
                )
            ],
            price,
        )
        long_estimate = estimate_run_cost(
            [
                ExtractedTokenUsage(
                    input_tokens=250000,
                    cached_input_tokens=100000,
                    output_tokens=1000,
                    total_tokens=251000,
                )
            ],
            price,
        )
    engine.dispose()

    assert short_estimate.input_usd_per_million == Decimal("1.250000")
    assert short_estimate.cached_input_usd_per_million == Decimal("0.125000")
    assert short_estimate.output_usd_per_million == Decimal("10.000000")
    assert short_estimate.input_cost_usd == Decimal("0.137500")
    assert short_estimate.output_cost_usd == Decimal("0.010000")
    assert short_estimate.total_cost_usd == Decimal("0.147500")
    assert long_estimate.input_usd_per_million == Decimal("2.500000")
    assert long_estimate.cached_input_usd_per_million == Decimal("0.250000")
    assert long_estimate.output_usd_per_million == Decimal("15.000000")
    assert long_estimate.input_cost_usd == Decimal("0.400000")
    assert long_estimate.output_cost_usd == Decimal("0.015000")
    assert long_estimate.total_cost_usd == Decimal("0.415000")


def test_init_db_upgrades_existing_sqlite_request_records_with_route_metadata(tmp_path) -> None:
    db_path = tmp_path / "old.sqlite3"
    settings = Settings(database_url=f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE request_records (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO request_records (id) VALUES (42)"))

    init_db(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("request_records")}
    price_columns = {column["name"] for column in inspector.get_columns("model_prices")}
    tier_columns = {column["name"] for column in inspector.get_columns("model_price_tiers")}
    indexes = {index["name"] for index in inspector.get_indexes("request_records")}
    with engine.connect() as connection:
        ids = connection.execute(text("SELECT id FROM request_records")).scalars().all()
    engine.dispose()

    assert {
        "task_run_id",
        "upstream_model",
        "model_route",
        "billing_provider_slug",
        "billing_model",
        "billing_input_tokens",
        "billing_cached_input_tokens",
        "billing_output_tokens",
        "billing_total_tokens",
        "billing_total_cost_usd",
        "pricing_snapshot_json",
        "upstream_response_body_raw",
        "response_was_rewritten",
        "compat_fixes_json",
        "compat_fix_errors_json",
        "estimated_input_tokens",
        "estimated_input_tokenizer",
        "estimated_input_model",
    }.issubset(columns)
    assert "cached_input_usd_per_million" in price_columns
    assert {"source_url", "checked_at", "release_date"}.issubset(price_columns)
    assert {
        "model_price_id",
        "min_input_tokens",
        "max_input_tokens",
        "input_usd_per_million",
        "cached_input_usd_per_million",
        "output_usd_per_million",
        "source_url",
        "checked_at",
        "release_date",
    }.issubset(tier_columns)
    assert {
        "ix_request_records_task_run_id",
        "ix_request_records_upstream_model",
        "ix_request_records_model_route",
        "ix_request_records_billing_provider_slug",
        "ix_request_records_billing_model",
        "ix_request_records_billing_cached_input_tokens",
        "ix_request_records_response_was_rewritten",
    }.issubset(indexes)
    assert ids == [42]
