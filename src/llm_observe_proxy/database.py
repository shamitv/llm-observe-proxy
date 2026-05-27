from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    case,
    create_engine,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    contains_eager,
    mapped_column,
    relationship,
    selectinload,
    sessionmaker,
)

from llm_observe_proxy.compatibility import normalize_fix_ids
from llm_observe_proxy.config import (
    EXPOSED_INCOMING_HOST,
    VALID_MATCH_TYPES,
    ModelRoute,
    Settings,
    normalize_provider_slug,
    normalize_provider_url,
    normalize_upstream_url,
    parse_model_routes,
)

MODEL_ROUTES_SETTING_KEY = "model_routes_json"
DEFAULT_COMPAT_FIXES_SETTING_KEY = "default_compat_fixes_json"
DEFAULT_ROUTES_SEEDED_AT_SETTING_KEY = "default_routes_seeded_at"
DEFAULT_ROUTE_SEED_OWNER = "default-route-seed"
DEFAULT_ROUTE_SEED_PRIORITY = 90
DEFAULT_PRICING_CHECKED_AT = "2026-05-23"
DEFAULT_PRICING_SOURCE = (
    "Seeded static catalog checked on 2026-05-23. Verify provider pricing before "
    "high-volume use."
)
OPENAI_PRICING_URL = "https://openai.com/api/pricing/"
OPENAI_GPT55_URL = "https://developers.openai.com/api/docs/models/gpt-5.5"
OPENAI_GPT55_PRO_URL = "https://developers.openai.com/api/docs/models/gpt-5.5-pro"
OPENAI_GPT54_URL = "https://developers.openai.com/api/docs/models/gpt-5.4"
OPENAI_GPT54_MINI_URL = "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
OPENAI_GPT54_NANO_URL = "https://developers.openai.com/api/docs/models/gpt-5.4-nano"
OPENAI_GPT54_PRO_URL = "https://developers.openai.com/api/docs/models/gpt-5.4-pro"
ANTHROPIC_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
GOOGLE_GEMINI_PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"
ALIBABA_PRICING_URL = "https://www.alibabacloud.com/help/en/model-studio/model-pricing"
ALIBABA_CACHE_URL = "https://www.alibabacloud.com/help/en/model-studio/context-cache"
DEEPSEEK_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing"
XAI_PRICING_URL = "https://docs.x.ai/developers/pricing"
ZAI_PRICING_URL = "https://docs.z.ai/guides/overview/pricing"
KIMI_K26_PRICING_URL = "https://platform.kimi.ai/docs/pricing/chat-k26"
KIMI_K25_PRICING_URL = "https://platform.kimi.ai/docs/pricing/chat-k25"
KIMI_K2_PRICING_URL = "https://platform.kimi.ai/docs/pricing/chat-k2"
MISTRAL_API_URL = "https://docs.mistral.ai/api"
MISTRAL_DEVSTRAL_URL = "https://docs.mistral.ai/models/model-cards/devstral-2-25-12"
MISTRAL_SMALL_URL = "https://docs.mistral.ai/models/model-cards/mistral-small-4-0-26-03"
MISTRAL_MEDIUM_URL = "https://docs.mistral.ai/models/model-cards/mistral-medium-3-5-26-04"
MISTRAL_LARGE_URL = "https://docs.mistral.ai/models/model-cards/mistral-large-3-25-12"
MISTRAL_MINISTRAL_3B_URL = "https://docs.mistral.ai/models/model-cards/ministral-3-3b-25-12"
MISTRAL_MINISTRAL_14B_URL = "https://docs.mistral.ai/models/model-cards/ministral-3-14b-25-12"
MISTRAL_CODESTRAL_URL = "https://docs.mistral.ai/models/model-cards/codestral-25-08"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
HF_ROUTER_MODELS_URL = "https://huggingface.co/inference/models"
GPT_OSS_RELEASE_URL = "https://openai.com/index/introducing-gpt-oss/"
IBM_GRANITE_RELEASE_URL = (
    "https://www.ibm.com/new/announcements/"
    "ibm-granite-4-0-hyper-efficient-high-performance-hybrid-models"
)
DEFAULT_MODEL_PROVIDERS = (
    {
        "slug": "local-llm",
        "name": "Local LLM",
        "upstream_url": "http://localhost:8000/v1",
        "currency": "USD",
        "api_key_env": None,
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":false}',
    },
    {
        "slug": "openai",
        "name": "OpenAI",
        "upstream_url": "https://api.openai.com/v1",
        "currency": "USD",
        "api_key_env": "OPENAI_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "anthropic",
        "name": "Anthropic",
        "upstream_url": "https://api.anthropic.com/v1",
        "currency": "USD",
        "api_key_env": "ANTHROPIC_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "google",
        "name": "Google Gemini",
        "upstream_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "currency": "USD",
        "api_key_env": "GEMINI_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "alibaba",
        "name": "Alibaba Cloud Model Studio",
        "upstream_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "currency": "USD",
        "api_key_env": "DASHSCOPE_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "deepseek",
        "name": "DeepSeek",
        "upstream_url": "https://api.deepseek.com/v1",
        "currency": "USD",
        "api_key_env": "DEEPSEEK_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true}',
    },
    {
        "slug": "xai",
        "name": "xAI",
        "upstream_url": "https://api.x.ai/v1",
        "currency": "USD",
        "api_key_env": "XAI_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "zai",
        "name": "Z.ai",
        "upstream_url": "https://api.z.ai/api/paas/v4",
        "currency": "USD",
        "api_key_env": "ZAI_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true}',
    },
    {
        "slug": "moonshot",
        "name": "Moonshot Kimi",
        "upstream_url": "https://api.moonshot.ai/v1",
        "currency": "USD",
        "api_key_env": "MOONSHOT_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true}',
    },
    {
        "slug": "mistral",
        "name": "Mistral AI",
        "upstream_url": "https://api.mistral.ai/v1",
        "currency": "USD",
        "api_key_env": "MISTRAL_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true}',
    },
    {
        "slug": "openrouter",
        "name": "OpenRouter",
        "upstream_url": "https://openrouter.ai/api/v1",
        "currency": "USD",
        "api_key_env": "OPENROUTER_API_KEY",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
    {
        "slug": "huggingface-router",
        "name": "Hugging Face Router",
        "upstream_url": "https://router.huggingface.co/v1",
        "currency": "USD",
        "api_key_env": "HF_TOKEN",
        "capabilities_json": '{"text":true,"tool_calling":true,"vision":true}',
    },
)
DEFAULT_MODEL_PRICES = (
    {
        "provider_slug": "openai",
        "model": "gpt-5.5",
        "display_name": "GPT-5.5",
        "input_usd_per_million": "5.00",
        "cached_input_usd_per_million": "0.50",
        "output_usd_per_million": "30.00",
        "source_url": OPENAI_GPT55_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-23",
        "notes": (
            "Official OpenAI text-token rates. Long prompts over 272K input "
            "tokens have a documented surcharge not represented in this scalar row."
        ),
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.5-pro",
        "display_name": "GPT-5.5 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "source_url": OPENAI_GPT55_PRO_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-23",
        "notes": "Official OpenAI text-token rates; cached input discount is not offered.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4",
        "display_name": "GPT-5.4",
        "input_usd_per_million": "2.50",
        "cached_input_usd_per_million": "0.25",
        "output_usd_per_million": "15.00",
        "source_url": OPENAI_GPT54_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-05",
        "notes": (
            "Official OpenAI text-token rates. Long prompts over 272K input "
            "tokens have a documented surcharge not represented in this scalar row."
        ),
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "input_usd_per_million": "0.75",
        "cached_input_usd_per_million": "0.075",
        "output_usd_per_million": "4.50",
        "source_url": OPENAI_GPT54_MINI_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-17",
        "notes": "Official OpenAI text-token rates.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "input_usd_per_million": "0.20",
        "cached_input_usd_per_million": "0.02",
        "output_usd_per_million": "1.25",
        "source_url": OPENAI_GPT54_NANO_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-17",
        "notes": "Official OpenAI text-token rates.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "source_url": OPENAI_GPT54_PRO_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-05",
        "notes": (
            "Official OpenAI text-token rates; no cached-input discount is listed. "
            "Long prompts over 272K input tokens have a documented surcharge not "
            "represented in this scalar row."
        ),
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-opus-4-7",
        "display_name": "Claude Opus 4.7",
        "input_usd_per_million": "5.00",
        "cached_input_usd_per_million": "0.50",
        "output_usd_per_million": "25.00",
        "source_url": ANTHROPIC_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-16",
        "notes": "Official Anthropic global rates; cached input uses cache-hit pricing.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "input_usd_per_million": "5.00",
        "cached_input_usd_per_million": "0.50",
        "output_usd_per_million": "25.00",
        "source_url": ANTHROPIC_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-02-17",
        "notes": "Official Anthropic global rates; cached input uses cache-hit pricing.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-sonnet-4-6",
        "display_name": "Claude Sonnet 4.6",
        "input_usd_per_million": "3.00",
        "cached_input_usd_per_million": "0.30",
        "output_usd_per_million": "15.00",
        "source_url": ANTHROPIC_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-02-17",
        "notes": "Official Anthropic global rates; cached input uses cache-hit pricing.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "input_usd_per_million": "1.00",
        "cached_input_usd_per_million": "0.10",
        "output_usd_per_million": "5.00",
        "source_url": ANTHROPIC_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-10-16",
        "notes": "Official Anthropic global rates; cached input uses cache-hit pricing.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3.1-pro-preview",
        "display_name": "Gemini 3.1 Pro Preview",
        "input_usd_per_million": "2.00",
        "cached_input_usd_per_million": "0.20",
        "output_usd_per_million": "12.00",
        "aliases": ("google/gemini-3.1-pro-preview",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-01",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash Preview",
        "input_usd_per_million": "0.50",
        "output_usd_per_million": "3.00",
        "aliases": ("google/gemini-3-flash-preview",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-17",
        "notes": (
            "Official Gemini API standard text-token rates. Context caching is not "
            "listed for this preview row."
        ),
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "input_usd_per_million": "1.25",
        "cached_input_usd_per_million": "0.125",
        "output_usd_per_million": "10.00",
        "aliases": ("google/gemini-2.5-pro",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-06-17",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
        "tiers": (
            ("<=200K", 0, 200001, "1.25", "0.125", "10.00"),
            (">200K", 200001, None, "2.50", "0.25", "15.00"),
        ),
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "input_usd_per_million": "0.30",
        "cached_input_usd_per_million": "0.03",
        "output_usd_per_million": "2.50",
        "aliases": ("google/gemini-2.5-flash",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-06-17",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash-Lite",
        "input_usd_per_million": "0.10",
        "cached_input_usd_per_million": "0.01",
        "output_usd_per_million": "0.40",
        "aliases": ("google/gemini-2.5-flash-lite",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-22",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3.5-flash",
        "display_name": "Gemini 3.5 Flash",
        "input_usd_per_million": "1.50",
        "cached_input_usd_per_million": "0.15",
        "output_usd_per_million": "9.00",
        "aliases": ("google/gemini-3.5-flash",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-05-20",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3.1-flash-lite",
        "display_name": "Gemini 3.1 Flash-Lite",
        "input_usd_per_million": "0.25",
        "cached_input_usd_per_million": "0.025",
        "output_usd_per_million": "1.50",
        "aliases": ("google/gemini-3.1-flash-lite",),
        "source_url": GOOGLE_GEMINI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-01",
        "notes": "Official Gemini API paid-tier standard text-token rates.",
    },
    {
        "provider_slug": "alibaba",
        "model": "qwen3-coder-plus",
        "display_name": "Qwen3 Coder Plus",
        "input_usd_per_million": "0.574",
        "cached_input_usd_per_million": "0.1148",
        "output_usd_per_million": "2.294",
        "aliases": ("qwen/qwen3-coder-plus", "qwen3-coder-plus-2025-09-23"),
        "source_url": ALIBABA_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-09-23",
        "notes": (
            "Global Model Studio rates. Cached input uses implicit cache at 20% of "
            f"input rate per {ALIBABA_CACHE_URL}."
        ),
        "tiers": (
            ("0-32K", 0, 32001, "0.574", "0.1148", "2.294"),
            ("32K-128K", 32001, 128001, "0.861", "0.1722", "3.441"),
            ("128K-256K", 128001, 256001, "1.434", "0.2868", "5.735"),
            ("256K-1M", 256001, 1000001, "2.868", "0.5736", "28.671"),
        ),
    },
    {
        "provider_slug": "alibaba",
        "model": "qwen3-coder-flash",
        "display_name": "Qwen3 Coder Flash",
        "input_usd_per_million": "0.144",
        "cached_input_usd_per_million": "0.0288",
        "output_usd_per_million": "0.574",
        "aliases": ("qwen/qwen3-coder-flash", "qwen3-coder-flash-2025-07-28"),
        "source_url": ALIBABA_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-28",
        "notes": (
            "Global Model Studio rates. Cached input uses implicit cache at 20% of "
            f"input rate per {ALIBABA_CACHE_URL}."
        ),
        "tiers": (
            ("0-32K", 0, 32001, "0.144", "0.0288", "0.574"),
            ("32K-128K", 32001, 128001, "0.216", "0.0432", "0.861"),
            ("128K-256K", 128001, 256001, "0.359", "0.0718", "1.434"),
            ("256K-1M", 256001, 1000001, "0.717", "0.1434", "3.584"),
        ),
    },
    {
        "provider_slug": "alibaba",
        "model": "qwen3-coder-480b-a35b-instruct",
        "display_name": "Qwen3 Coder 480B A35B Instruct",
        "input_usd_per_million": "0.861",
        "output_usd_per_million": "3.441",
        "aliases": ("qwen/qwen3-coder", "Qwen/Qwen3-Coder-480B-A35B-Instruct"),
        "source_url": ALIBABA_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-22",
        "notes": "Global Model Studio Qwen3-Coder open-weight model rates.",
        "tiers": (
            ("0-32K", 0, 32001, "0.861", "", "3.441"),
            ("32K-128K", 32001, 128001, "1.291", "", "5.161"),
            ("128K-200K", 128001, 200001, "2.151", "", "8.602"),
        ),
    },
    {
        "provider_slug": "alibaba",
        "model": "qwen3-coder-next",
        "display_name": "Qwen3 Coder Next",
        "input_usd_per_million": "0.30",
        "output_usd_per_million": "1.50",
        "aliases": ("qwen/qwen3-coder-next", "Qwen/Qwen3-Coder-Next"),
        "source_url": ALIBABA_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-01",
        "notes": (
            "Official Alibaba Model Studio International deployment rates. "
            "Context Cache support is not listed for this model."
        ),
        "tiers": (
            ("0-32K", 0, 32001, "0.30", "", "1.50"),
            ("32K-128K", 32001, 128001, "0.50", "", "2.50"),
            ("128K-256K", 128001, 256001, "0.80", "", "4.00"),
        ),
    },
    {
        "provider_slug": "alibaba",
        "model": "qwen3-coder-30b-a3b-instruct",
        "display_name": "Qwen3 Coder 30B A3B Instruct",
        "input_usd_per_million": "0.216",
        "output_usd_per_million": "0.861",
        "aliases": ("qwen/qwen3-coder-30b-a3b-instruct", "Qwen/Qwen3-Coder-30B-A3B-Instruct"),
        "source_url": ALIBABA_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-31",
        "notes": "Official Alibaba Model Studio Global deployment rates.",
        "tiers": (
            ("0-32K", 0, 32001, "0.216", "", "0.861"),
            ("32K-128K", 32001, 128001, "0.323", "", "1.291"),
            ("128K-200K", 128001, 200001, "0.538", "", "2.151"),
        ),
    },
    {
        "provider_slug": "deepseek",
        "model": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "input_usd_per_million": "0.14",
        "cached_input_usd_per_million": "0.0028",
        "output_usd_per_million": "0.28",
        "aliases": ("deepseek-chat", "deepseek/deepseek-v4-flash"),
        "source_url": DEEPSEEK_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-24",
        "notes": (
            "DeepSeek notes deepseek-chat maps to the non-thinking V4 Flash "
            "compatibility mode."
        ),
    },
    {
        "provider_slug": "deepseek",
        "model": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "input_usd_per_million": "0.435",
        "cached_input_usd_per_million": "0.003625",
        "output_usd_per_million": "0.87",
        "aliases": ("deepseek-reasoner", "deepseek/deepseek-v4-pro"),
        "source_url": DEEPSEEK_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-24",
        "notes": (
            "Official page lists 75% off pricing until 2026-05-31 and a "
            "post-promo adjustment."
        ),
    },
    {
        "provider_slug": "xai",
        "model": "grok-4.3",
        "display_name": "Grok 4.3",
        "input_usd_per_million": "1.25",
        "cached_input_usd_per_million": "0.20",
        "output_usd_per_million": "2.50",
        "aliases": ("grok-4.3-latest", "grok-latest"),
        "source_url": XAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-05-15",
        "notes": "Official xAI pricing lists input, cached input, and output token rates.",
    },
    {
        "provider_slug": "xai",
        "model": "grok-build-0.1",
        "display_name": "Grok Build 0.1",
        "input_usd_per_million": "1.00",
        "cached_input_usd_per_million": "0.20",
        "output_usd_per_million": "2.00",
        "source_url": XAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-05-15",
        "notes": "Official xAI pricing lists input, cached input, and output token rates.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-5.1",
        "display_name": "GLM-5.1",
        "input_usd_per_million": "1.40",
        "cached_input_usd_per_million": "0.26",
        "output_usd_per_million": "4.40",
        "aliases": ("z-ai/glm-5.1", "zai-org/GLM-5.1-FP8"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-08",
        "notes": "Official Z.ai model pricing. Cached input storage listed as limited-time free.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-4.7",
        "display_name": "GLM-4.7",
        "input_usd_per_million": "0.60",
        "cached_input_usd_per_million": "0.11",
        "output_usd_per_million": "2.20",
        "aliases": ("z-ai/glm-4.7", "zai-org/GLM-4.7"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-22",
        "notes": "Official Z.ai model pricing. Cached input storage listed as limited-time free.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-4.7-flashx",
        "display_name": "GLM-4.7 FlashX",
        "input_usd_per_million": "0.07",
        "cached_input_usd_per_million": "0.01",
        "output_usd_per_million": "0.40",
        "aliases": ("z-ai/glm-4.7-flashx", "zai-org/GLM-4.7-FlashX"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-01-19",
        "notes": "Official Z.ai model pricing. Cached input storage listed as limited-time free.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-4.7-flash",
        "display_name": "GLM-4.7 Flash",
        "input_usd_per_million": "0",
        "cached_input_usd_per_million": "0",
        "output_usd_per_million": "0",
        "aliases": ("z-ai/glm-4.7-flash", "zai-org/GLM-4.7-Flash"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-01-19",
        "notes": "Official Z.ai pricing lists GLM-4.7-Flash as free.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-4.5",
        "display_name": "GLM-4.5",
        "input_usd_per_million": "0.60",
        "cached_input_usd_per_million": "0.11",
        "output_usd_per_million": "2.20",
        "aliases": ("z-ai/glm-4.5", "zai-org/GLM-4.5"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-25",
        "notes": "Official Z.ai model pricing. Cached input storage listed as limited-time free.",
    },
    {
        "provider_slug": "zai",
        "model": "glm-4.5-air",
        "display_name": "GLM-4.5 Air",
        "input_usd_per_million": "0.20",
        "cached_input_usd_per_million": "0.03",
        "output_usd_per_million": "1.10",
        "aliases": ("z-ai/glm-4.5-air", "zai-org/GLM-4.5-Air"),
        "source_url": ZAI_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-25",
        "notes": "Official Z.ai model pricing. Cached input storage listed as limited-time free.",
    },
    {
        "provider_slug": "moonshot",
        "model": "kimi-k2.6",
        "display_name": "Kimi K2.6",
        "input_usd_per_million": "0.95",
        "cached_input_usd_per_million": "0.16",
        "output_usd_per_million": "4.00",
        "aliases": ("moonshotai/kimi-k2.6", "kimi-k2.6-preview"),
        "source_url": KIMI_K26_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-05-18",
        "notes": (
            "Official Kimi page lists input price as cache miss and cached input "
            "as cache hit."
        ),
    },
    {
        "provider_slug": "moonshot",
        "model": "kimi-k2.5",
        "display_name": "Kimi K2.5",
        "input_usd_per_million": "0.60",
        "cached_input_usd_per_million": "0.10",
        "output_usd_per_million": "3.00",
        "aliases": ("moonshotai/kimi-k2.5", "moonshotai/Kimi-K2.5"),
        "source_url": KIMI_K25_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-01-01",
        "notes": (
            "Official Kimi page lists input price as cache miss and cached input "
            "as cache hit."
        ),
    },
    {
        "provider_slug": "moonshot",
        "model": "kimi-k2-0905-preview",
        "display_name": "Kimi K2 0905 Preview",
        "input_usd_per_million": "0.60",
        "cached_input_usd_per_million": "0.15",
        "output_usd_per_million": "2.50",
        "aliases": ("moonshotai/kimi-k2-0905", "moonshotai/kimi-k2"),
        "source_url": KIMI_K2_PRICING_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-09-05",
        "notes": (
            "Official page says Kimi K2 series retires on 2026-05-25; seed remains "
            "for historical runs."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "devstral-2512",
        "display_name": "Devstral 2",
        "input_usd_per_million": "0.40",
        "cached_input_usd_per_million": "0.04",
        "output_usd_per_million": "2.00",
        "aliases": ("mistralai/devstral-2512", "devstral-2-25-12"),
        "source_url": MISTRAL_DEVSTRAL_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-09",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "mistral-small-2603",
        "display_name": "Mistral Small 4",
        "input_usd_per_million": "0.15",
        "cached_input_usd_per_million": "0.015",
        "output_usd_per_million": "0.60",
        "aliases": ("mistralai/mistral-small-2603", "mistral-small-4-0-26-03"),
        "source_url": MISTRAL_SMALL_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-16",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "mistral-medium-2604",
        "display_name": "Mistral Medium 3.5",
        "input_usd_per_million": "1.50",
        "cached_input_usd_per_million": "0.15",
        "output_usd_per_million": "7.50",
        "aliases": ("mistralai/mistral-medium-3-5", "mistral-medium-3-5-26-04"),
        "source_url": MISTRAL_MEDIUM_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-30",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "mistral-large-2512",
        "display_name": "Mistral Large 3",
        "input_usd_per_million": "0.50",
        "cached_input_usd_per_million": "0.05",
        "output_usd_per_million": "1.50",
        "aliases": ("mistralai/mistral-large-2512", "mistral-large-3-25-12"),
        "source_url": MISTRAL_LARGE_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-02",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "ministral-3b-2512",
        "display_name": "Ministral 3 3B",
        "input_usd_per_million": "0.10",
        "cached_input_usd_per_million": "0.01",
        "output_usd_per_million": "0.10",
        "aliases": ("mistralai/ministral-3b-2512",),
        "source_url": MISTRAL_MINISTRAL_3B_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-02",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "ministral-14b-2512",
        "display_name": "Ministral 3 14B",
        "input_usd_per_million": "0.20",
        "cached_input_usd_per_million": "0.02",
        "output_usd_per_million": "0.20",
        "aliases": ("mistralai/ministral-14b-2512",),
        "source_url": MISTRAL_MINISTRAL_14B_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-02",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "mistral",
        "model": "codestral-2508",
        "display_name": "Codestral 2508",
        "input_usd_per_million": "0.30",
        "cached_input_usd_per_million": "0.03",
        "output_usd_per_million": "0.90",
        "aliases": ("mistralai/codestral-2508",),
        "source_url": MISTRAL_CODESTRAL_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-30",
        "notes": (
            "Official model-card rates; cached tokens billed at 10% of input per "
            f"{MISTRAL_API_URL}."
        ),
    },
    {
        "provider_slug": "openrouter",
        "model": "openai/gpt-oss-120b",
        "display_name": "OpenAI gpt-oss-120b (OpenRouter)",
        "input_usd_per_million": "0.039",
        "output_usd_per_million": "0.18",
        "aliases": ("gpt-oss-120b",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-08-05",
        "notes": f"Router fallback for OpenAI open-weight model released at {GPT_OSS_RELEASE_URL}.",
    },
    {
        "provider_slug": "openrouter",
        "model": "openai/gpt-oss-20b",
        "display_name": "OpenAI gpt-oss-20b (OpenRouter)",
        "input_usd_per_million": "0.030",
        "output_usd_per_million": "0.14",
        "aliases": ("gpt-oss-20b",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-08-05",
        "notes": f"Router fallback for OpenAI open-weight model released at {GPT_OSS_RELEASE_URL}.",
    },
    {
        "provider_slug": "openrouter",
        "model": "ibm-granite/granite-4.0-h-micro",
        "display_name": "IBM Granite 4.0 H Micro (OpenRouter)",
        "input_usd_per_million": "0.017",
        "output_usd_per_million": "0.112",
        "aliases": ("granite-4.0-h-micro",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-10-02",
        "notes": f"Router fallback; IBM release source: {IBM_GRANITE_RELEASE_URL}.",
    },
    {
        "provider_slug": "openrouter",
        "model": "minimax/minimax-m2.1",
        "display_name": "MiniMax M2.1 (OpenRouter)",
        "input_usd_per_million": "0.29",
        "cached_input_usd_per_million": "0.03",
        "output_usd_per_million": "0.95",
        "aliases": ("MiniMaxAI/MiniMax-M2.1",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-23",
        "notes": "Router fallback. Cache write prices are not billed by v0.4 cost math.",
    },
    {
        "provider_slug": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "display_name": "DeepSeek V3.2 (OpenRouter)",
        "input_usd_per_million": "0.252",
        "cached_input_usd_per_million": "0.0252",
        "output_usd_per_million": "0.378",
        "aliases": ("DeepSeek-V3.2",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-01",
        "notes": "Router fallback because current official DeepSeek API lists V4 model IDs.",
    },
    {
        "provider_slug": "openrouter",
        "model": "qwen/qwen3-coder",
        "display_name": "Qwen3 Coder 480B A35B (OpenRouter)",
        "input_usd_per_million": "0.22",
        "output_usd_per_million": "1.80",
        "aliases": ("Qwen/Qwen3-Coder-480B-A35B-Instruct",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-23",
        "notes": "Router fallback for Qwen3 Coder open-weight model.",
    },
    {
        "provider_slug": "openrouter",
        "model": "qwen/qwen3.6-27b",
        "display_name": "Qwen3.6 27B (OpenRouter)",
        "input_usd_per_million": "0.30",
        "cached_input_usd_per_million": "0.15",
        "output_usd_per_million": "2.00",
        "aliases": ("Qwen/Qwen3.6-27B", "qwen3.6-27b", "qwen-3.6-27b"),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-22",
        "notes": "OpenRouter fallback row for Qwen3.6 27B.",
    },
    {
        "provider_slug": "openrouter",
        "model": "qwen/qwen3.6-27b@chutes/fp8",
        "display_name": "Qwen3.6 27B (Chutes, OpenRouter)",
        "input_usd_per_million": "0.30",
        "cached_input_usd_per_million": "0.15",
        "output_usd_per_million": "2.00",
        "aliases": ("qwen/qwen3.6-27b:chutes/fp8",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-22",
        "notes": "OpenRouter endpoint row; route generation pins provider order.",
    },
    {
        "provider_slug": "openrouter",
        "model": "google/gemma-4-26b-a4b-it",
        "display_name": "Gemma 4 26B A4B IT (OpenRouter)",
        "input_usd_per_million": "0.07",
        "output_usd_per_million": "0.34",
        "aliases": (
            "google/gemma-4-26B-A4B-it",
            "gemma-4-26b",
            "gemma-4-26b-a4b-it",
        ),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-03",
        "notes": "OpenRouter fallback row for Gemma 4 26B A4B IT.",
    },
    {
        "provider_slug": "openrouter",
        "model": "google/gemma-4-26b-a4b-it@deepinfra/fp8",
        "display_name": "Gemma 4 26B A4B IT (DeepInfra, OpenRouter)",
        "input_usd_per_million": "0.07",
        "output_usd_per_million": "0.34",
        "aliases": ("google/gemma-4-26b-a4b-it:deepinfra/fp8",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-04-03",
        "notes": "OpenRouter endpoint row; route generation pins provider order.",
    },
    {
        "provider_slug": "openrouter",
        "model": "deepseek/deepseek-v3.2-speciale",
        "display_name": "DeepSeek V3.2 Speciale (OpenRouter)",
        "input_usd_per_million": "0.287",
        "cached_input_usd_per_million": "0.058",
        "output_usd_per_million": "0.431",
        "aliases": ("DeepSeek-V3.2-Speciale",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-01",
        "notes": "Router fallback because current official DeepSeek API lists V4 model IDs.",
    },
    {
        "provider_slug": "openrouter",
        "model": "minimax/minimax-m2.7",
        "display_name": "MiniMax M2.7 (OpenRouter)",
        "input_usd_per_million": "0.279",
        "output_usd_per_million": "1.20",
        "aliases": ("MiniMaxAI/MiniMax-M2.7",),
        "source_url": OPENROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-03-18",
        "notes": "Router fallback from the OpenRouter Models API.",
    },
    {
        "provider_slug": "huggingface-router",
        "model": "openai/gpt-oss-120b",
        "display_name": "OpenAI gpt-oss-120b (HF Router)",
        "input_usd_per_million": "0.05",
        "output_usd_per_million": "0.25",
        "source_url": HF_ROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-08-05",
        "notes": "Hugging Face router cheapest listed provider row; no HF markup per pricing docs.",
    },
    {
        "provider_slug": "huggingface-router",
        "model": "openai/gpt-oss-20b",
        "display_name": "OpenAI gpt-oss-20b (HF Router)",
        "input_usd_per_million": "0.04",
        "output_usd_per_million": "0.15",
        "source_url": HF_ROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-08-05",
        "notes": "Hugging Face router cheapest listed provider row; no HF markup per pricing docs.",
    },
    {
        "provider_slug": "huggingface-router",
        "model": "moonshotai/Kimi-K2.5",
        "display_name": "Kimi K2.5 (HF Router)",
        "input_usd_per_million": "0.60",
        "output_usd_per_million": "3.00",
        "aliases": ("moonshotai/kimi-k2.5",),
        "source_url": HF_ROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2026-01-01",
        "notes": "Hugging Face router listed provider row; no HF markup per pricing docs.",
    },
    {
        "provider_slug": "huggingface-router",
        "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "display_name": "Qwen3 Coder 30B A3B Instruct (HF Router)",
        "input_usd_per_million": "0.07",
        "output_usd_per_million": "0.26",
        "aliases": ("qwen/qwen3-coder-30b-a3b-instruct",),
        "source_url": HF_ROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-07-31",
        "notes": "Hugging Face router cheapest listed provider row.",
    },
    {
        "provider_slug": "huggingface-router",
        "model": "MiniMaxAI/MiniMax-M2.1",
        "display_name": "MiniMax M2.1 (HF Router)",
        "input_usd_per_million": "0.30",
        "output_usd_per_million": "1.20",
        "aliases": ("minimax/minimax-m2.1",),
        "source_url": HF_ROUTER_MODELS_URL,
        "checked_at": DEFAULT_PRICING_CHECKED_AT,
        "release_date": "2025-12-23",
        "notes": "Hugging Face router listed provider row.",
    },
)

_LEGACY_SCALAR_SEED_MODEL_PRICES = (
    {
        "provider_slug": "openai",
        "model": "gpt-5.5",
        "display_name": "GPT-5.5",
        "input_usd_per_million": "5.00",
        "output_usd_per_million": "30.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.5-pro",
        "display_name": "GPT-5.5 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4",
        "display_name": "GPT-5.4",
        "input_usd_per_million": "2.50",
        "output_usd_per_million": "15.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "input_usd_per_million": "0.75",
        "output_usd_per_million": "4.50",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "input_usd_per_million": "0.20",
        "output_usd_per_million": "1.25",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-opus-4-7",
        "display_name": "Claude Opus 4.7",
        "input_usd_per_million": "5.00",
        "output_usd_per_million": "25.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "input_usd_per_million": "5.00",
        "output_usd_per_million": "25.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-sonnet-4-6",
        "display_name": "Claude Sonnet 4.6",
        "input_usd_per_million": "3.00",
        "output_usd_per_million": "15.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "anthropic",
        "model": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "input_usd_per_million": "1.00",
        "output_usd_per_million": "5.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3.1-pro-preview",
        "display_name": "Gemini 3.1 Pro Preview",
        "input_usd_per_million": "2.00",
        "output_usd_per_million": "12.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash Preview",
        "input_usd_per_million": "0.50",
        "output_usd_per_million": "3.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "input_usd_per_million": "1.25",
        "output_usd_per_million": "10.00",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "input_usd_per_million": "0.30",
        "output_usd_per_million": "2.50",
        "notes": "Legacy scalar seed from v0.3.",
    },
    {
        "provider_slug": "google",
        "model": "gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash-Lite",
        "input_usd_per_million": "0.10",
        "output_usd_per_million": "0.40",
        "notes": "Legacy scalar seed from v0.3.",
    },
)

_OPENAI_PRE_METADATA_SEED_NOTE = (
    "Seeded from official standard paid text pricing checked on 2026-05-03."
)

_OPENAI_PRE_METADATA_SEED_MODEL_PRICES = (
    {
        "provider_slug": "openai",
        "model": "gpt-5.5",
        "display_name": "GPT-5.5",
        "input_usd_per_million": "5.00",
        "output_usd_per_million": "30.00",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.5-pro",
        "display_name": "GPT-5.5 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4",
        "display_name": "GPT-5.4",
        "input_usd_per_million": "2.50",
        "output_usd_per_million": "15.00",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "input_usd_per_million": "0.75",
        "output_usd_per_million": "4.50",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "input_usd_per_million": "0.20",
        "output_usd_per_million": "1.25",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "input_usd_per_million": "0.20",
        "cached_input_usd_per_million": "0.02",
        "output_usd_per_million": "1.25",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
    {
        "provider_slug": "openai",
        "model": "gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "input_usd_per_million": "30.00",
        "output_usd_per_million": "180.00",
        "notes": _OPENAI_PRE_METADATA_SEED_NOTE,
    },
)

DEFAULT_MODEL_PRICE_REVISIONS: dict[tuple[str, str], tuple[dict[str, object], ...]] = {}
for _revision_seed in (
    *_LEGACY_SCALAR_SEED_MODEL_PRICES,
    *_OPENAI_PRE_METADATA_SEED_MODEL_PRICES,
):
    _key = (str(_revision_seed["provider_slug"]), str(_revision_seed["model"]))
    DEFAULT_MODEL_PRICE_REVISIONS[_key] = (
        *DEFAULT_MODEL_PRICE_REVISIONS.get(_key, ()),
        _revision_seed,
    )


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    requests: Mapped[list[RequestRecord]] = relationship(back_populates="task_run")


class RequestRecord(Base):
    __tablename__ = "request_records"
    __table_args__ = (
        Index("ix_request_records_model_created_at", "model", "created_at"),
        Index("ix_request_records_model_route_created_at", "model_route", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    query_string: Mapped[str] = mapped_column(Text, default="")
    endpoint: Mapped[str] = mapped_column(String(512), index=True)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    upstream_model: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    model_route: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    upstream_url: Mapped[str] = mapped_column(Text)
    request_headers_json: Mapped[str] = mapped_column(Text)
    request_body: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    request_content_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    response_headers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    upstream_response_body_raw: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    response_content_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_stream: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_images: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_tool_calls: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_provider_slug: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    billing_provider_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    billing_model: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    billing_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_cached_input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    billing_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_input_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    billing_output_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    billing_total_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    pricing_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_was_rewritten: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    compat_fixes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    compat_fix_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_input_tokenizer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    estimated_input_model: Mapped[str | None] = mapped_column(String(256), nullable=True)

    images: Mapped[list[ImageAsset]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    task_run: Mapped[TaskRun | None] = relationship(back_populates="requests")


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("request_records.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(Text)
    data_base64: Mapped[str | None] = mapped_column(Text, nullable=True)

    record: Mapped[RequestRecord] = relationship(back_populates="images")


class ModelProvider(Base):
    __tablename__ = "model_providers"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    upstream_url: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    api_key_env: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    capabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )

    prices: Mapped[list[ModelPrice]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    routes: Mapped[list[ModelRouteDB]] = relationship(back_populates="provider")


class ModelRouteDB(Base):
    __tablename__ = "model_routes"
    __table_args__ = (
        UniqueConstraint("incoming_model", "match_type", name="uq_route_model_match"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incoming_model: Mapped[str] = mapped_column(String(256), index=True)
    match_type: Mapped[str] = mapped_column(String(32), default="exact")
    upstream_url: Mapped[str] = mapped_column(Text)
    upstream_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_slug: Mapped[str | None] = mapped_column(
        ForeignKey("model_providers.slug", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_key_env: Mapped[str | None] = mapped_column(String(128), nullable=True)
    compatibility_fixes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    managed_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    override_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )

    provider: Mapped[ModelProvider | None] = relationship(back_populates="routes")

    @property
    def model(self) -> str:
        return self.incoming_model

    @property
    def effective_upstream_model(self) -> str:
        return self.upstream_model or self.incoming_model

    @property
    def fixes(self) -> tuple[str, ...]:
        if not self.compatibility_fixes_json:
            return ()
        try:
            return normalize_fix_ids(json.loads(self.compatibility_fixes_json))
        except (json.JSONDecodeError, ValueError):
            return ()


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (UniqueConstraint("provider_slug", "model", name="uq_provider_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_slug: Mapped[str] = mapped_column(
        ForeignKey("model_providers.slug", ondelete="CASCADE"),
        index=True,
    )
    model: Mapped[str] = mapped_column(String(256), index=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    input_usd_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cached_input_usd_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    output_usd_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )

    provider: Mapped[ModelProvider] = relationship(back_populates="prices")
    tiers: Mapped[list[ModelPriceTier]] = relationship(
        back_populates="price",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ModelPriceTier.min_input_tokens",
    )


class ModelPriceTier(Base):
    __tablename__ = "model_price_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_price_id: Mapped[int] = mapped_column(
        ForeignKey("model_prices.id", ondelete="CASCADE"),
        index=True,
    )
    min_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_usd_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cached_input_usd_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    output_usd_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )

    price: Mapped[ModelPrice] = relationship(back_populates="tiers")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )


SessionFactory = sessionmaker[Session]


def create_db_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        _ensure_sqlite_parent(engine)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            if isinstance(dbapi_connection, SQLiteConnection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return engine


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_sqlite_task_run_schema(engine)
    _ensure_sqlite_request_record_schema(engine)
    _ensure_sqlite_model_provider_schema(engine)
    _ensure_sqlite_model_route_schema(engine)
    _ensure_sqlite_model_price_schema(engine)
    seed_default_model_pricing(engine)
    _migrate_json_blob_routes(engine)
    seed_default_model_routes_once(engine)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    setting = session.get(AppSetting, key)
    return setting.value if setting else default


def set_setting(session: Session, key: str, value: str) -> AppSetting:
    setting = session.get(AppSetting, key)
    if setting is None:
        setting = AppSetting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    session.flush()
    return setting


def get_upstream_url(session: Session, settings: Settings) -> str:
    return get_setting(session, "upstream_url", settings.upstream_url) or settings.upstream_url


def get_incoming_port(session: Session, settings: Settings) -> int:
    value = get_setting(session, "incoming_port")
    if value is None:
        return settings.incoming_port
    try:
        port = int(value)
    except ValueError:
        return settings.incoming_port
    if 1 <= port <= 65535:
        return port
    return settings.incoming_port


def get_expose_all_ips(session: Session, settings: Settings) -> bool:
    value = get_setting(session, "expose_all_ips")
    if value is None:
        return settings.expose_all_ips
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_incoming_host(session: Session, settings: Settings) -> str:
    if get_expose_all_ips(session, settings):
        return EXPOSED_INCOMING_HOST
    return settings.incoming_host


def set_incoming_server(session: Session, port: int, expose_all_ips: bool) -> None:
    set_setting(session, "incoming_port", str(port))
    set_setting(session, "expose_all_ips", "true" if expose_all_ips else "false")


def get_default_compat_fixes(session: Session, settings: Settings) -> tuple[str, ...]:
    value = get_setting(session, DEFAULT_COMPAT_FIXES_SETTING_KEY)
    if value is None:
        return settings.default_fixes
    try:
        return normalize_fix_ids(json.loads(value))
    except (json.JSONDecodeError, ValueError):
        return settings.default_fixes


def set_default_compat_fixes(session: Session, fix_ids: object) -> None:
    fixes = normalize_fix_ids(fix_ids)
    set_setting(
        session,
        DEFAULT_COMPAT_FIXES_SETTING_KEY,
        json.dumps(list(fixes), ensure_ascii=False, separators=(",", ":")),
    )


def get_default_provider_slug(session: Session) -> str | None:
    configured = normalize_provider_slug(get_setting(session, "default_provider_slug"))
    if configured:
        return configured
    provider = get_default_fallback_provider(session)
    return provider.slug if provider else None


def set_default_provider_slug(session: Session, slug: str | None) -> None:
    provider_slug = normalize_provider_slug(slug)
    if provider_slug is not None and session.get(ModelProvider, provider_slug) is None:
        raise ValueError("Default provider was not found.")
    if provider_slug:
        set_default_fallback_provider(session, provider_slug)
    else:
        set_setting(session, "default_provider_slug", "")


def get_default_model(session: Session) -> str | None:
    value = get_setting(session, "default_model")
    return value.strip() if value and value.strip() else None


def set_default_model(session: Session, model: str | None) -> None:
    set_setting(session, "default_model", (model or "").strip())


def is_fallback_enabled(session: Session) -> bool:
    value = get_setting(session, "fallback_enabled")
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def set_fallback_enabled(session: Session, enabled: bool) -> None:
    set_setting(session, "fallback_enabled", "true" if enabled else "false")


def get_default_fallback_provider(session: Session) -> ModelProvider | None:
    return session.scalar(
        select(ModelProvider)
        .where(ModelProvider.is_default_fallback.is_(True))
        .order_by(ModelProvider.name)
    )


def set_default_fallback_provider(session: Session, slug: str) -> ModelProvider:
    provider_slug = normalize_provider_slug(slug)
    if provider_slug is None:
        raise ValueError("Default provider is required.")
    provider = session.get(ModelProvider, provider_slug)
    if provider is None:
        raise ValueError("Default provider was not found.")
    if not provider.active:
        raise ValueError("Default provider must be active.")
    for existing in session.scalars(select(ModelProvider)).all():
        existing.is_default_fallback = existing.slug == provider_slug
    set_setting(session, "default_provider_slug", provider_slug)
    session.flush()
    return provider


def get_fallback_summary(session: Session) -> dict[str, object | None]:
    provider_slug = get_default_provider_slug(session)
    provider = session.get(ModelProvider, provider_slug) if provider_slug else None
    model = get_default_model(session)
    return {
        "enabled": is_fallback_enabled(session),
        "provider_slug": provider.slug if provider else provider_slug,
        "provider_name": provider.name if provider else None,
        "model": model,
        "upstream_url": provider.upstream_url if provider else None,
    }


def list_model_providers(session: Session) -> list[ModelProvider]:
    return list(session.scalars(select(ModelProvider).order_by(ModelProvider.name)).all())


def list_active_model_providers(session: Session) -> list[ModelProvider]:
    return list(
        session.scalars(
            select(ModelProvider)
            .where(ModelProvider.active.is_(True))
            .order_by(ModelProvider.name)
        ).all()
    )


def list_model_prices(session: Session) -> list[ModelPrice]:
    return list(
        session.scalars(
            select(ModelPrice)
            .join(ModelProvider)
            .options(contains_eager(ModelPrice.provider), selectinload(ModelPrice.tiers))
            .order_by(ModelProvider.name, ModelPrice.model)
        ).all()
    )


def get_provider_usage_summary(session: Session) -> list[dict[str, object]]:
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    usage_rows = {
        row[0]: {
            "requests_today": int(row[1] or 0),
            "estimated_cost_usd": float(row[2] or 0),
        }
        for row in session.execute(
            select(
                RequestRecord.billing_provider_slug,
                func.count(RequestRecord.id),
                func.coalesce(func.sum(RequestRecord.billing_total_cost_usd), 0),
            )
            .where(RequestRecord.created_at >= today_start)
            .where(RequestRecord.billing_provider_slug.is_not(None))
            .group_by(RequestRecord.billing_provider_slug)
        )
    }
    route_counts = {
        row[0]: int(row[1] or 0)
        for row in session.execute(
            select(ModelRouteDB.provider_slug, func.count(ModelRouteDB.id))
            .where(ModelRouteDB.active.is_(True))
            .where(ModelRouteDB.provider_slug.is_not(None))
            .group_by(ModelRouteDB.provider_slug)
        )
    }
    summaries: list[dict[str, object]] = []
    for provider in list_model_providers(session):
        usage = usage_rows.get(provider.slug, {})
        summaries.append(
            {
                "provider_slug": provider.slug,
                "provider_name": provider.name,
                "requests_today": usage.get("requests_today", 0),
                "estimated_cost_usd": usage.get("estimated_cost_usd", 0.0),
                "active_routes": route_counts.get(provider.slug, 0),
            }
        )
    return summaries


def get_route_usage_summary(session: Session) -> list[dict[str, object]]:
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = session.execute(
        select(
            RequestRecord.model_route,
            func.count(RequestRecord.id),
            func.max(RequestRecord.created_at),
        )
        .where(RequestRecord.created_at >= today_start)
        .where(RequestRecord.model_route.is_not(None))
        .group_by(RequestRecord.model_route)
    ).all()
    return [
        {
            "route": row[0],
            "requests_today": int(row[1] or 0),
            "last_matched_at": (
                row[2].isoformat().replace("+00:00", "Z") if isinstance(row[2], datetime) else None
            ),
        }
        for row in rows
    ]


def upsert_model_provider(
    session: Session,
    *,
    slug: str,
    name: str,
    upstream_url: str = "",
    currency: str = "USD",
    api_key_env: str = "",
    active: bool = True,
    is_default_fallback: bool = False,
    capabilities: object = None,
) -> ModelProvider:
    provider_slug = normalize_provider_slug(slug)
    if provider_slug is None:
        raise ValueError("Provider slug is required.")

    provider_name = name.strip()
    if not provider_name:
        raise ValueError("Provider name is required.")

    provider_currency = (currency.strip() or "USD").upper()
    if not provider_currency.isascii() or len(provider_currency) > 16:
        raise ValueError("Provider currency must be a short ASCII value.")

    normalized_url = normalize_provider_url(upstream_url)
    if normalized_url:
        existing = session.scalar(
            select(ModelProvider).where(ModelProvider.upstream_url == normalized_url)
        )
        if existing is not None and existing.slug != provider_slug:
            raise ValueError("Provider URL is already assigned to another provider.")

    provider = session.get(ModelProvider, provider_slug)
    if provider is None:
        provider = ModelProvider(slug=provider_slug, name=provider_name)
        session.add(provider)

    provider.name = provider_name
    provider.upstream_url = normalized_url
    provider.currency = provider_currency
    provider.api_key_env = _optional_metadata(api_key_env, "API key environment variable")
    provider.active = bool(active)
    provider.capabilities_json = _capabilities_json(capabilities)
    if is_default_fallback:
        if not provider.active:
            raise ValueError("Default fallback provider must be active.")
        session.flush()
        set_default_fallback_provider(session, provider.slug)
    else:
        provider.is_default_fallback = bool(provider.is_default_fallback)
    session.flush()
    return provider


def delete_model_provider(session: Session, slug: str) -> bool:
    provider_slug = normalize_provider_slug(slug)
    if provider_slug is None:
        return False
    provider = session.get(ModelProvider, provider_slug)
    if provider is None:
        return False
    session.delete(provider)
    return True


def list_model_routes_db(session: Session, *, active_only: bool = False) -> list[ModelRouteDB]:
    stmt = select(ModelRouteDB).order_by(ModelRouteDB.priority, ModelRouteDB.id)
    if active_only:
        stmt = stmt.where(ModelRouteDB.active.is_(True))
    return list(session.scalars(stmt).all())


def get_model_route_db(session: Session, route_id: int) -> ModelRouteDB | None:
    return session.get(ModelRouteDB, route_id)


def upsert_model_route_db(
    session: Session,
    *,
    incoming_model: str,
    match_type: str = "exact",
    upstream_url: str,
    upstream_model: str = "",
    provider_slug: str = "",
    api_key_env: str = "",
    compatibility_fixes: object = None,
    override_fallback: bool = False,
    priority: int | str = 50,
    active: bool = True,
    managed_by: str | None = None,
    route_id: int | None = None,
) -> ModelRouteDB:
    pattern = incoming_model.strip()
    if not pattern:
        raise ValueError("Incoming model is required.")
    resolved_match_type = match_type.strip().lower()
    if resolved_match_type not in VALID_MATCH_TYPES:
        raise ValueError("Match type must be exact or prefix.")
    normalized_url = normalize_upstream_url(upstream_url)
    try:
        resolved_priority = int(priority)
    except (TypeError, ValueError):
        raise ValueError("Route priority must be a number.") from None
    if not 1 <= resolved_priority <= 100:
        raise ValueError("Route priority must be between 1 and 100.")

    resolved_provider_slug = normalize_provider_slug(provider_slug)
    if resolved_provider_slug and session.get(ModelProvider, resolved_provider_slug) is None:
        raise ValueError("Provider was not found.")

    fixes = normalize_fix_ids(compatibility_fixes)
    existing = session.scalar(
        select(ModelRouteDB).where(
            ModelRouteDB.incoming_model == pattern,
            ModelRouteDB.match_type == resolved_match_type,
        )
    )
    if existing is not None and (route_id is None or existing.id != route_id):
        raise ValueError("A route with this incoming model and match type already exists.")

    route = session.get(ModelRouteDB, route_id) if route_id is not None else existing
    if route_id is not None and route is None:
        raise ValueError("Model route was not found.")
    if route is None:
        route = ModelRouteDB(incoming_model=pattern, match_type=resolved_match_type)
        session.add(route)

    route.incoming_model = pattern
    route.match_type = resolved_match_type
    route.upstream_url = normalized_url
    route.upstream_model = _optional_metadata(upstream_model, "Upstream model", max_length=256)
    route.provider_slug = resolved_provider_slug
    route.api_key_env = _optional_metadata(api_key_env, "API key environment variable")
    route.compatibility_fixes_json = (
        json.dumps(list(fixes), ensure_ascii=False, separators=(",", ":")) if fixes else None
    )
    route.managed_by = _optional_metadata(managed_by, "Managed by", max_length=64)
    route.override_fallback = bool(override_fallback)
    route.priority = resolved_priority
    route.active = bool(active)
    session.flush()
    return route


def delete_model_route_db(session: Session, route_id: int) -> bool:
    route = session.get(ModelRouteDB, route_id)
    if route is None:
        return False
    session.delete(route)
    session.flush()
    return True


def upsert_model_price(
    session: Session,
    *,
    provider_slug: str,
    model: str,
    input_usd_per_million: object,
    output_usd_per_million: object,
    cached_input_usd_per_million: object = "",
    aliases: str | list[str] | tuple[str, ...] = "",
    display_name: str = "",
    active: bool = True,
    source_url: str = "",
    checked_at: str = "",
    release_date: str = "",
    notes: str = "",
) -> ModelPrice:
    resolved_provider_slug = normalize_provider_slug(provider_slug)
    if resolved_provider_slug is None:
        raise ValueError("Provider is required.")
    provider = session.get(ModelProvider, resolved_provider_slug)
    if provider is None:
        raise ValueError("Provider was not found.")

    resolved_model = model.strip()
    if not resolved_model:
        raise ValueError("Model is required.")

    input_rate = _decimal_rate(input_usd_per_million, "Input price")
    cached_input_rate = _optional_decimal_rate(
        cached_input_usd_per_million,
        "Cached input price",
    )
    output_rate = _decimal_rate(output_usd_per_million, "Output price")
    price = session.scalar(
        select(ModelPrice).where(
            ModelPrice.provider_slug == resolved_provider_slug,
            ModelPrice.model == resolved_model,
        )
    )
    if price is None:
        price = ModelPrice(provider_slug=resolved_provider_slug, model=resolved_model)
        session.add(price)

    price.display_name = display_name.strip() or None
    price.aliases_json = _aliases_json(aliases)
    price.input_usd_per_million = input_rate
    price.cached_input_usd_per_million = cached_input_rate
    price.output_usd_per_million = output_rate
    price.active = active
    price.source_url = _optional_metadata(source_url, "Source URL", max_length=2048)
    price.checked_at = _optional_metadata(checked_at, "Checked date")
    price.release_date = _optional_metadata(release_date, "Release date")
    price.notes = notes.strip() or None
    session.flush()
    return price


def upsert_model_price_tier(
    session: Session,
    *,
    model_price_id: int,
    input_usd_per_million: object,
    output_usd_per_million: object,
    cached_input_usd_per_million: object = "",
    min_input_tokens: object = "",
    max_input_tokens: object = "",
    label: str = "",
    source_url: str = "",
    checked_at: str = "",
    release_date: str = "",
    notes: str = "",
    tier_id: int | None = None,
) -> ModelPriceTier:
    price = session.get(ModelPrice, model_price_id)
    if price is None:
        raise ValueError("Model price was not found.")

    minimum = _optional_token_bound(min_input_tokens, "Minimum input tokens")
    maximum = _optional_token_bound(max_input_tokens, "Maximum input tokens")
    _validate_tier_bounds(minimum, maximum)

    tier = session.get(ModelPriceTier, tier_id) if tier_id is not None else None
    if tier_id is not None and (tier is None or tier.model_price_id != model_price_id):
        raise ValueError("Model price tier was not found.")
    _validate_non_overlapping_tier(
        session,
        price.id,
        minimum,
        maximum,
        tier.id if tier else None,
    )

    if tier is None:
        tier = ModelPriceTier(model_price_id=model_price_id)
        session.add(tier)
    tier.min_input_tokens = minimum
    tier.max_input_tokens = maximum
    tier.input_usd_per_million = _decimal_rate(input_usd_per_million, "Tier input price")
    tier.cached_input_usd_per_million = _optional_decimal_rate(
        cached_input_usd_per_million,
        "Tier cached input price",
    )
    tier.output_usd_per_million = _decimal_rate(output_usd_per_million, "Tier output price")
    tier.label = label.strip() or None
    tier.source_url = _optional_metadata(source_url, "Tier source URL", max_length=2048)
    tier.checked_at = _optional_metadata(checked_at, "Tier checked date")
    tier.release_date = _optional_metadata(release_date, "Tier release date")
    tier.notes = notes.strip() or None
    session.flush()
    return tier


def delete_model_price_tier(session: Session, tier_id: int) -> bool:
    tier = session.get(ModelPriceTier, tier_id)
    if tier is None:
        return False
    session.delete(tier)
    session.flush()
    return True


def delete_model_price(session: Session, provider_slug: str, model: str) -> bool:
    try:
        resolved_provider_slug = normalize_provider_slug(provider_slug)
    except ValueError:
        return False
    resolved_model = model.strip()
    if resolved_provider_slug is None or not resolved_model:
        return False
    price = session.scalar(
        select(ModelPrice).where(
            ModelPrice.provider_slug == resolved_provider_slug,
            ModelPrice.model == resolved_model,
        )
    )
    if price is None:
        return False
    session.delete(price)
    return True


@dataclass(frozen=True)
class DefaultRouteCandidate:
    incoming_model: str
    upstream_url: str
    upstream_model: str
    provider_slug: str
    api_key_env: str | None
    priority: int
    source_model: str
    source_alias: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.incoming_model, "exact")

    @property
    def cost_sort_value(self) -> Decimal:
        return Decimal("0")


ROUTER_PROVIDER_SLUGS = frozenset({"huggingface-router", "openrouter"})


def build_default_model_route_candidates(
    session: Session,
    *,
    provider_slug: str | None = None,
) -> list[DefaultRouteCandidate]:
    resolved_provider_slug = normalize_provider_slug(provider_slug)
    stmt = (
        select(ModelPrice)
        .join(ModelProvider)
        .options(contains_eager(ModelPrice.provider))
        .where(ModelPrice.active.is_(True))
        .where(ModelProvider.active.is_(True))
        .where(ModelProvider.upstream_url.is_not(None))
        .order_by(ModelProvider.name, ModelPrice.model)
    )
    if resolved_provider_slug:
        stmt = stmt.where(ModelPrice.provider_slug == resolved_provider_slug)
    prices = list(session.scalars(stmt).all())
    cheapest_router_models = _cheapest_router_endpoint_models(prices)
    candidates: list[tuple[tuple[object, ...], DefaultRouteCandidate]] = []

    for price in prices:
        provider = price.provider
        if provider is None or not provider.upstream_url:
            continue
        try:
            upstream_url = normalize_upstream_url(provider.upstream_url)
        except ValueError:
            continue
        upstream_model = _default_route_upstream_model(price, cheapest_router_models)
        for incoming_model, alias in _default_route_incoming_models(price):
            candidate = DefaultRouteCandidate(
                incoming_model=incoming_model,
                upstream_url=upstream_url,
                upstream_model=upstream_model,
                provider_slug=provider.slug,
                api_key_env=provider.api_key_env,
                priority=DEFAULT_ROUTE_SEED_PRIORITY,
                source_model=price.model,
                source_alias=alias,
            )
            candidates.append((_default_route_candidate_sort_key(candidate, price), candidate))

    deduped: dict[tuple[str, str], DefaultRouteCandidate] = {}
    for _sort_key, candidate in sorted(candidates, key=lambda item: item[0]):
        deduped.setdefault(candidate.key, candidate)
    return sorted(
        deduped.values(),
        key=lambda candidate: (candidate.provider_slug, candidate.incoming_model),
    )


def preview_default_model_routes(
    session: Session,
    *,
    provider_slug: str | None = None,
    mode: str = "missing_only",
) -> dict[str, object]:
    candidates = build_default_model_route_candidates(session, provider_slug=provider_slug)
    return _default_route_seed_summary(session, candidates, mode=mode, apply=False)


def apply_default_model_routes(
    session: Session,
    *,
    provider_slug: str | None = None,
    mode: str = "missing_only",
) -> dict[str, object]:
    candidates = build_default_model_route_candidates(session, provider_slug=provider_slug)
    summary = _default_route_seed_summary(session, candidates, mode=mode, apply=True)
    set_setting(session, DEFAULT_ROUTES_SEEDED_AT_SETTING_KEY, _now().isoformat())
    return summary


def seed_default_model_routes_once(engine: Engine) -> None:
    with Session(engine) as session:
        if get_setting(session, DEFAULT_ROUTES_SEEDED_AT_SETTING_KEY):
            return
        apply_default_model_routes(session, mode="missing_only")
        session.commit()


def _default_route_seed_summary(
    session: Session,
    candidates: list[DefaultRouteCandidate],
    *,
    mode: str,
    apply: bool,
) -> dict[str, object]:
    resolved_mode = mode.strip().lower() if mode else "missing_only"
    if resolved_mode not in {"missing_only", "refresh_seeded"}:
        raise ValueError("Default route mode must be missing_only or refresh_seeded.")

    inserted = 0
    updated = 0
    skipped_existing = 0
    skipped_user = 0
    items: list[dict[str, object]] = []
    for candidate in candidates:
        existing = session.scalar(
            select(ModelRouteDB).where(
                ModelRouteDB.incoming_model == candidate.incoming_model,
                ModelRouteDB.match_type == "exact",
            )
        )
        status = "insert"
        route_id = None
        if existing is not None:
            route_id = existing.id
            if existing.managed_by != DEFAULT_ROUTE_SEED_OWNER:
                skipped_user += 1
                status = "skip_user_route"
            elif resolved_mode == "refresh_seeded":
                updated += 1
                status = "update_seeded_route"
            else:
                skipped_existing += 1
                status = "skip_existing_seeded_route"
        else:
            inserted += 1

        if apply and status in {"insert", "update_seeded_route"}:
            upsert_model_route_db(
                session,
                route_id=route_id,
                incoming_model=candidate.incoming_model,
                match_type="exact",
                upstream_url=candidate.upstream_url,
                upstream_model=candidate.upstream_model,
                provider_slug=candidate.provider_slug,
                api_key_env=candidate.api_key_env or "",
                compatibility_fixes=(),
                priority=candidate.priority,
                active=True,
                managed_by=DEFAULT_ROUTE_SEED_OWNER,
            )
        items.append(_default_route_candidate_row(candidate, status))

    return {
        "mode": resolved_mode,
        "managed_by": DEFAULT_ROUTE_SEED_OWNER,
        "total_candidates": len(candidates),
        "inserted": inserted,
        "updated": updated,
        "skipped_existing": skipped_existing,
        "skipped_user": skipped_user,
        "items": items[:200],
        "truncated": len(items) > 200,
    }


def _default_route_candidate_row(
    candidate: DefaultRouteCandidate,
    status: str,
) -> dict[str, object]:
    return {
        "incoming_model": candidate.incoming_model,
        "match_type": "exact",
        "upstream_url": candidate.upstream_url,
        "upstream_model": candidate.upstream_model,
        "provider_slug": candidate.provider_slug,
        "api_key_env": candidate.api_key_env,
        "priority": candidate.priority,
        "source_model": candidate.source_model,
        "source_alias": candidate.source_alias,
        "status": status,
    }


def _default_route_incoming_models(price: ModelPrice) -> list[tuple[str, str | None]]:
    incoming = [(price.model, None)]
    if price.provider_slug == "openrouter" and "@" in price.model:
        base_model, provider_tag = _split_openrouter_endpoint_model(price.model)
        if base_model and provider_tag:
            incoming.append((f"{base_model}:{provider_tag}", price.model))
    for alias in _model_price_aliases(price):
        incoming.append((alias, alias))

    deduped: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for model, alias in incoming:
        normalized = model.strip()
        if normalized and normalized not in seen:
            deduped.append((normalized, alias))
            seen.add(normalized)
    return deduped


def _default_route_upstream_model(
    price: ModelPrice,
    cheapest_router_models: dict[tuple[str, str], str],
) -> str:
    base_model = _router_base_model(price.provider_slug, price.model)
    if base_model is None or base_model != price.model:
        return price.model
    return cheapest_router_models.get((price.provider_slug, base_model), price.model)


def _cheapest_router_endpoint_models(prices: list[ModelPrice]) -> dict[tuple[str, str], str]:
    endpoint_rows: dict[tuple[str, str], list[ModelPrice]] = {}
    for price in prices:
        base_model = _router_base_model(price.provider_slug, price.model)
        if base_model is None or base_model == price.model:
            continue
        endpoint_rows.setdefault((price.provider_slug, base_model), []).append(price)

    cheapest: dict[tuple[str, str], str] = {}
    for key, rows in endpoint_rows.items():
        selected = min(rows, key=_router_endpoint_price_sort_key)
        cheapest[key] = selected.model
    return cheapest


def _router_endpoint_price_sort_key(price: ModelPrice) -> tuple[Decimal, int, str]:
    total = (price.input_usd_per_million or Decimal("0")) + (
        price.output_usd_per_million or Decimal("0")
    )
    cached_rank = 0 if price.cached_input_usd_per_million is not None else 1
    return (total, cached_rank, price.model)


def _router_base_model(provider_slug: str | None, model: str) -> str | None:
    if provider_slug == "openrouter":
        base_model, provider_tag = _split_openrouter_endpoint_model(model)
        return base_model if provider_tag else model
    if provider_slug == "huggingface-router":
        base_model, separator, provider_name = model.rpartition(":")
        if base_model and separator and provider_name:
            return base_model
        return model
    return None


def _split_openrouter_endpoint_model(model: str) -> tuple[str | None, str | None]:
    base_model, separator, provider_tag = model.partition("@")
    if not separator or not base_model or not provider_tag:
        return None, None
    return base_model, provider_tag


def _default_route_candidate_sort_key(
    candidate: DefaultRouteCandidate,
    price: ModelPrice,
) -> tuple[object, ...]:
    alias_rank = 0 if candidate.source_alias is None else 1
    provider_rank = 1 if candidate.provider_slug in ROUTER_PROVIDER_SLUGS else 0
    total = (price.input_usd_per_million or Decimal("0")) + (
        price.output_usd_per_million or Decimal("0")
    )
    return (
        candidate.incoming_model,
        alias_rank,
        provider_rank,
        total,
        candidate.provider_slug,
        candidate.source_model,
    )


def _model_price_aliases(price: ModelPrice) -> list[str]:
    if not price.aliases_json:
        return []
    try:
        aliases = json.loads(price.aliases_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(aliases, list):
        return []
    return [alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip()]


def seed_default_model_pricing(engine: Engine) -> None:
    with Session(engine) as session:
        for provider_data in DEFAULT_MODEL_PROVIDERS:
            provider = session.get(ModelProvider, provider_data["slug"])
            if provider is None:
                session.add(ModelProvider(**provider_data))
            else:
                if not provider.api_key_env:
                    provider.api_key_env = provider_data.get("api_key_env")
                if not provider.capabilities_json:
                    provider.capabilities_json = provider_data.get("capabilities_json")
                if provider.active is None:
                    provider.active = True
        session.flush()

        for price_data in DEFAULT_MODEL_PRICES:
            provider_slug = str(price_data["provider_slug"])
            model = str(price_data["model"])
            existing = session.scalar(
                select(ModelPrice).where(
                    ModelPrice.provider_slug == provider_slug,
                    ModelPrice.model == model,
                )
            )
            if existing is not None:
                previous_seeds = DEFAULT_MODEL_PRICE_REVISIONS.get((provider_slug, model), ())
                if any(
                    _model_price_matches_seed_for_revision(existing, previous_seed)
                    for previous_seed in previous_seeds
                ):
                    _apply_model_price_seed(existing, price_data)
                continue
            price = ModelPrice(
                provider_slug=provider_slug,
                model=model,
            )
            _apply_model_price_seed(price, price_data)
            session.add(price)
        session.commit()


def get_ui_model_routes(session: Session) -> tuple[ModelRoute, ...]:
    return tuple(
        ModelRoute(
            model=route.incoming_model,
            upstream_url=route.upstream_url,
            upstream_model=route.upstream_model,
            provider_slug=route.provider_slug,
            api_key_env=route.api_key_env,
            fixes=route.fixes,
        )
        for route in list_model_routes_db(session)
    )


def get_effective_model_routes(session: Session, settings: Settings) -> tuple[ModelRoute, ...]:
    return (*settings.model_routes, *get_ui_model_routes(session))


def upsert_ui_model_route(session: Session, settings: Settings, route: ModelRoute) -> None:
    if route.model in {configured.model for configured in settings.model_routes}:
        raise ValueError("Model route already exists in startup configuration.")

    existing = session.scalar(
        select(ModelRouteDB).where(
            ModelRouteDB.incoming_model == route.model,
            ModelRouteDB.match_type == "exact",
        )
    )
    upsert_model_route_db(
        session,
        route_id=existing.id if existing else None,
        incoming_model=route.model,
        match_type="exact",
        upstream_url=route.upstream_url,
        upstream_model=route.upstream_model or "",
        provider_slug=route.provider_slug or "",
        api_key_env=route.api_key_env or "",
        compatibility_fixes=route.fixes,
        priority=50,
        active=True,
    )


def delete_ui_model_route(session: Session, model: str) -> bool:
    resolved_model = model.strip()
    route = session.scalar(
        select(ModelRouteDB).where(
            ModelRouteDB.incoming_model == resolved_model,
            ModelRouteDB.match_type == "exact",
        )
    )
    if route is None:
        return False
    session.delete(route)
    return True


def get_active_task_run(session: Session) -> TaskRun | None:
    return session.scalar(
        select(TaskRun)
        .where(TaskRun.ended_at.is_(None), TaskRun.paused_at.is_(None))
        .order_by(TaskRun.started_at.desc())
    )


def start_task_run(session: Session, name: str, notes: str | None = None) -> TaskRun:
    resolved_name = name.strip()
    if not resolved_name:
        raise ValueError("Run name is required.")

    now = _now()
    active_runs = session.scalars(
        select(TaskRun).where(TaskRun.ended_at.is_(None), TaskRun.paused_at.is_(None))
    ).all()
    for active_run in active_runs:
        active_run.ended_at = now

    task_run = TaskRun(name=resolved_name, notes=notes.strip() if notes else None, started_at=now)
    session.add(task_run)
    session.flush()
    return task_run


def end_active_task_run(session: Session) -> TaskRun | None:
    active_run = get_active_task_run(session)
    if active_run is None:
        return None
    active_run.ended_at = _now()
    session.flush()
    return active_run


def pause_active_task_run(session: Session) -> TaskRun | None:
    active_run = get_active_task_run(session)
    if active_run is None:
        return None
    active_run.paused_at = _now()
    session.flush()
    return active_run


def resume_task_run(session: Session, task_run_id: int) -> TaskRun:
    task_run = session.get(TaskRun, task_run_id)
    if task_run is None:
        raise LookupError("Run not found.")
    if task_run.ended_at is not None:
        raise ValueError("Completed runs cannot be resumed.")

    now = _now()
    active_runs = session.scalars(
        select(TaskRun).where(
            TaskRun.id != task_run_id,
            TaskRun.ended_at.is_(None),
            TaskRun.paused_at.is_(None),
        )
    ).all()
    for active_run in active_runs:
        active_run.paused_at = now
    task_run.paused_at = None
    session.flush()
    return task_run


def get_task_run_stats(session: Session, task_run_id: int) -> dict[str, object]:
    stats = session.execute(
        select(
            func.count(RequestRecord.id),
            func.min(RequestRecord.created_at),
            func.max(RequestRecord.completed_at),
            func.coalesce(func.sum(RequestRecord.duration_ms), 0),
            func.coalesce(func.sum(case((RequestRecord.is_stream.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(case((RequestRecord.has_images.is_(True), 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((RequestRecord.has_tool_calls.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(func.sum(case((RequestRecord.error.is_not(None), 1), else_=0)), 0),
        ).where(RequestRecord.task_run_id == task_run_id)
    ).one()
    request_count = int(stats[0] or 0)
    first_request_at = stats[1]
    last_completed_at = stats[2]
    total_request_duration_ms = int(stats[3] or 0)
    return {
        "request_count": request_count,
        "first_request_at": first_request_at,
        "last_completed_at": last_completed_at,
        "llm_wall_time_ms": _duration_ms(first_request_at, last_completed_at),
        "total_request_duration_ms": total_request_duration_ms,
        "streams": int(stats[4] or 0),
        "images": int(stats[5] or 0),
        "tools": int(stats[6] or 0),
        "errors": int(stats[7] or 0),
    }


def list_task_runs_with_stats(session: Session, limit: int = 100) -> list[dict[str, object]]:
    runs = session.scalars(
        select(TaskRun).order_by(TaskRun.started_at.desc()).limit(limit)
    ).all()
    return [
        {
            "run": task_run,
            "stats": get_task_run_stats(session, task_run.id),
        }
        for task_run in runs
    ]


def _ensure_sqlite_parent(engine: Engine) -> None:
    database = engine.url.database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _ensure_sqlite_task_run_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "task_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("task_runs")}
    with engine.begin() as connection:
        if "paused_at" not in columns:
            connection.execute(text("ALTER TABLE task_runs ADD COLUMN paused_at DATETIME"))


def _ensure_sqlite_request_record_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "request_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("request_records")}
    with engine.begin() as connection:
        if "task_run_id" not in columns:
            connection.execute(text("ALTER TABLE request_records ADD COLUMN task_run_id INTEGER"))
        if "upstream_model" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN upstream_model VARCHAR(256)")
            )
        if "model_route" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN model_route VARCHAR(256)")
            )
        if "billing_provider_slug" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_provider_slug VARCHAR(64)")
            )
        if "billing_provider_name" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_provider_name VARCHAR(128)")
            )
        if "billing_model" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_model VARCHAR(256)")
            )
        if "billing_input_tokens" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_input_tokens INTEGER")
            )
        if "billing_cached_input_tokens" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_cached_input_tokens INTEGER")
            )
        if "billing_output_tokens" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_output_tokens INTEGER")
            )
        if "billing_total_tokens" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_total_tokens INTEGER")
            )
        if "billing_input_cost_usd" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_input_cost_usd NUMERIC")
            )
        if "billing_output_cost_usd" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_output_cost_usd NUMERIC")
            )
        if "billing_total_cost_usd" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN billing_total_cost_usd NUMERIC")
            )
        if "pricing_snapshot_json" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN pricing_snapshot_json TEXT")
            )
        if "upstream_response_body_raw" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN upstream_response_body_raw BLOB")
            )
        if "response_was_rewritten" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE request_records ADD COLUMN "
                    "response_was_rewritten BOOLEAN DEFAULT 0"
                )
            )
        if "compat_fixes_json" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN compat_fixes_json TEXT")
            )
        if "compat_fix_errors_json" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN compat_fix_errors_json TEXT")
            )
        if "estimated_input_tokens" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN estimated_input_tokens INTEGER")
            )
        if "estimated_input_tokenizer" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE request_records ADD COLUMN "
                    "estimated_input_tokenizer VARCHAR(128)"
                )
            )
        if "estimated_input_model" not in columns:
            connection.execute(
                text("ALTER TABLE request_records ADD COLUMN estimated_input_model VARCHAR(256)")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_records_created_at "
                "ON request_records (created_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_records_model_created_at "
                "ON request_records (model, created_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_records_model_route_created_at "
                "ON request_records (model_route, created_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_task_run_id ON request_records (task_run_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_upstream_model ON request_records (upstream_model)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_model_route ON request_records (model_route)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_billing_provider_slug "
                "ON request_records (billing_provider_slug)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_billing_model ON request_records (billing_model)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_billing_cached_input_tokens "
                "ON request_records (billing_cached_input_tokens)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_request_records_response_was_rewritten "
                "ON request_records (response_was_rewritten)"
            )
        )


def _ensure_sqlite_model_provider_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "model_providers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("model_providers")}
    with engine.begin() as connection:
        if "api_key_env" not in columns:
            connection.execute(
                text("ALTER TABLE model_providers ADD COLUMN api_key_env VARCHAR(128)")
            )
        if "active" not in columns:
            connection.execute(
                text("ALTER TABLE model_providers ADD COLUMN active BOOLEAN DEFAULT 1")
            )
        if "is_default_fallback" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE model_providers ADD COLUMN "
                    "is_default_fallback BOOLEAN DEFAULT 0"
                )
            )
        if "capabilities_json" not in columns:
            connection.execute(
                text("ALTER TABLE model_providers ADD COLUMN capabilities_json TEXT")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_model_providers_active ON model_providers (active)"
            )
        )


def _ensure_sqlite_model_route_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "model_routes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("model_routes")}
    with engine.begin() as connection:
        if "managed_by" not in columns:
            connection.execute(text("ALTER TABLE model_routes ADD COLUMN managed_by VARCHAR(64)"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_model_routes_managed_by ON model_routes (managed_by)"
            )
        )


def _ensure_sqlite_model_price_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "model_prices" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("model_prices")}
    with engine.begin() as connection:
        if "cached_input_usd_per_million" not in columns:
            connection.execute(
                text("ALTER TABLE model_prices ADD COLUMN cached_input_usd_per_million NUMERIC")
            )
        if "source_url" not in columns:
            connection.execute(text("ALTER TABLE model_prices ADD COLUMN source_url TEXT"))
        if "checked_at" not in columns:
            connection.execute(text("ALTER TABLE model_prices ADD COLUMN checked_at VARCHAR(32)"))
        if "release_date" not in columns:
            connection.execute(text("ALTER TABLE model_prices ADD COLUMN release_date VARCHAR(32)"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_model_price_tiers_model_price_id "
                "ON model_price_tiers (model_price_id)"
            )
        )


def _migrate_json_blob_routes(engine: Engine) -> None:
    with Session(engine) as session:
        unmanaged_routes = session.scalar(
            select(func.count())
            .select_from(ModelRouteDB)
            .where(
                (ModelRouteDB.managed_by.is_(None))
                | (ModelRouteDB.managed_by != DEFAULT_ROUTE_SEED_OWNER)
            )
        )
        if unmanaged_routes:
            return
        value = get_setting(session, MODEL_ROUTES_SETTING_KEY)
        if not value:
            return
        try:
            routes = parse_model_routes(json.loads(value))
        except (json.JSONDecodeError, ValueError):
            return
        for route in routes:
            upsert_model_route_db(
                session,
                incoming_model=route.model,
                match_type="exact",
                upstream_url=route.upstream_url,
                upstream_model=route.upstream_model or "",
                provider_slug=route.provider_slug or "",
                api_key_env=route.api_key_env or "",
                compatibility_fixes=route.fixes,
                priority=50,
                active=True,
            )
        setting = session.get(AppSetting, MODEL_ROUTES_SETTING_KEY)
        if setting is not None:
            session.delete(setting)
        session.commit()


def _set_ui_model_routes(session: Session, routes: list[ModelRoute]) -> None:
    payload = [
        {
            "model": route.model,
            "upstream_url": route.upstream_url,
            **({"upstream_model": route.upstream_model} if route.upstream_model else {}),
            **({"provider_slug": route.provider_slug} if route.provider_slug else {}),
            **({"api_key_env": route.api_key_env} if route.api_key_env else {}),
            **({"fixes": list(route.fixes)} if route.fixes else {}),
        }
        for route in routes
    ]
    set_setting(session, MODEL_ROUTES_SETTING_KEY, json.dumps(payload, separators=(",", ":")))


def _decimal_rate(value: object, label: str) -> Decimal:
    try:
        rate = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a valid number.") from None
    if rate < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return rate


def _seed_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _seed_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _seed_decimal(value)


def _optional_decimal_rate(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _decimal_rate(value, label)


def _optional_token_bound(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        bound = int(str(value).strip())
    except ValueError:
        raise ValueError(f"{label} must be a whole number.") from None
    if bound < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return bound


def _validate_tier_bounds(minimum: int | None, maximum: int | None) -> None:
    normalized_minimum = minimum if minimum is not None else 0
    if maximum is not None and maximum <= normalized_minimum:
        raise ValueError("Maximum input tokens must be greater than minimum input tokens.")


def _validate_non_overlapping_tier(
    session: Session,
    model_price_id: int,
    minimum: int | None,
    maximum: int | None,
    tier_id: int | None,
) -> None:
    new_min = minimum if minimum is not None else 0
    new_max = maximum
    tiers = session.scalars(
        select(ModelPriceTier).where(ModelPriceTier.model_price_id == model_price_id)
    ).all()
    for existing in tiers:
        if tier_id is not None and existing.id == tier_id:
            continue
        existing_min = existing.min_input_tokens if existing.min_input_tokens is not None else 0
        existing_max = existing.max_input_tokens
        lower_overlaps = existing_max is None or new_min < existing_max
        upper_overlaps = new_max is None or existing_min < new_max
        if lower_overlaps and upper_overlaps:
            raise ValueError("Model price tier overlaps an existing tier.")


def _optional_metadata(value: object, label: str, *, max_length: int = 32) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    if not text_value.isascii() or len(text_value) > max_length:
        raise ValueError(f"{label} must be ASCII and at most {max_length} characters.")
    return text_value


def _capabilities_json(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            decoded = json.loads(text_value)
        except json.JSONDecodeError:
            raise ValueError("Capabilities must be valid JSON.") from None
    elif isinstance(value, dict):
        decoded = value
    else:
        raise ValueError("Capabilities must be a JSON object.")
    if not isinstance(decoded, dict):
        raise ValueError("Capabilities must be a JSON object.")
    allowed = {"text", "vision", "tool_calling"}
    normalized = {key: bool(decoded.get(key)) for key in allowed if key in decoded}
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")) if normalized else None


def _aliases_json(value: str | list[str] | tuple[str, ...]) -> str | None:
    if isinstance(value, str):
        aliases = [
            alias.strip()
            for chunk in value.splitlines()
            for alias in chunk.split(",")
            if alias.strip()
        ]
    else:
        aliases = [alias.strip() for alias in value if isinstance(alias, str) and alias.strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias not in seen:
            deduped.append(alias)
            seen.add(alias)
    if not deduped:
        return None
    return json.dumps(deduped, ensure_ascii=False, separators=(",", ":"))


def _seed_metadata(value: object) -> str | None:
    return str(value or "") or None


def _seed_price_tier_snapshot(tier: ModelPriceTier) -> tuple[object, ...]:
    return (
        tier.label,
        tier.min_input_tokens,
        tier.max_input_tokens,
        tier.input_usd_per_million,
        tier.cached_input_usd_per_million,
        tier.output_usd_per_million,
        tier.source_url,
        tier.checked_at,
        tier.release_date,
        tier.notes,
    )


def _seed_data_tier_snapshot(price_data: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    source_url = _seed_metadata(price_data.get("source_url"))
    checked_at = _seed_metadata(price_data.get("checked_at"))
    release_date = _seed_metadata(price_data.get("release_date"))
    notes = str(price_data.get("notes") or DEFAULT_PRICING_SOURCE)
    snapshots: list[tuple[object, ...]] = []
    for tier_data in price_data.get("tiers", ()):
        label, minimum, maximum, input_rate, cached_input_rate, output_rate = tier_data
        snapshots.append(
            (
                label,
                minimum,
                maximum,
                _seed_decimal(input_rate),
                _seed_optional_decimal(cached_input_rate),
                _seed_decimal(output_rate),
                source_url,
                checked_at,
                release_date,
                notes,
            )
        )
    return tuple(snapshots)


def _model_price_matches_seed(price: ModelPrice, price_data: dict[str, object]) -> bool:
    if price.display_name != _seed_metadata(price_data.get("display_name")):
        return False
    if price.aliases_json != _aliases_json(price_data.get("aliases", "")):
        return False
    if price.input_usd_per_million != _seed_decimal(price_data["input_usd_per_million"]):
        return False
    if price.cached_input_usd_per_million != _seed_optional_decimal(
        price_data.get("cached_input_usd_per_million")
    ):
        return False
    if price.output_usd_per_million != _seed_decimal(price_data["output_usd_per_million"]):
        return False
    if bool(price.active) != bool(price_data.get("active", True)):
        return False
    if price.source_url != _seed_metadata(price_data.get("source_url")):
        return False
    if price.checked_at != _seed_metadata(price_data.get("checked_at")):
        return False
    if price.release_date != _seed_metadata(price_data.get("release_date")):
        return False
    if price.notes != str(price_data.get("notes") or DEFAULT_PRICING_SOURCE):
        return False
    return tuple(_seed_price_tier_snapshot(tier) for tier in price.tiers) == (
        _seed_data_tier_snapshot(price_data)
    )


def _model_price_matches_seed_for_revision(
    price: ModelPrice,
    price_data: dict[str, object],
) -> bool:
    if price.display_name != _seed_metadata(price_data.get("display_name")):
        return False
    if price.aliases_json != _aliases_json(price_data.get("aliases", "")):
        return False
    if price.input_usd_per_million != _seed_decimal(price_data["input_usd_per_million"]):
        return False
    if "cached_input_usd_per_million" in price_data and price.cached_input_usd_per_million != (
        _seed_optional_decimal(price_data.get("cached_input_usd_per_million"))
    ):
        return False
    if price.output_usd_per_million != _seed_decimal(price_data["output_usd_per_million"]):
        return False
    if bool(price.active) != bool(price_data.get("active", True)):
        return False
    return tuple(_seed_price_tier_snapshot(tier) for tier in price.tiers) == (
        _seed_data_tier_snapshot(price_data)
    )


def _apply_model_price_seed(price: ModelPrice, price_data: dict[str, object]) -> None:
    price.display_name = _seed_metadata(price_data.get("display_name"))
    price.aliases_json = _aliases_json(price_data.get("aliases", ""))
    price.input_usd_per_million = _seed_decimal(price_data["input_usd_per_million"])
    price.cached_input_usd_per_million = _seed_optional_decimal(
        price_data.get("cached_input_usd_per_million")
    )
    price.output_usd_per_million = _seed_decimal(price_data["output_usd_per_million"])
    price.active = bool(price_data.get("active", True))
    price.source_url = _seed_metadata(price_data.get("source_url"))
    price.checked_at = _seed_metadata(price_data.get("checked_at"))
    price.release_date = _seed_metadata(price_data.get("release_date"))
    price.notes = str(price_data.get("notes") or DEFAULT_PRICING_SOURCE)
    price.tiers.clear()
    for tier_data in price_data.get("tiers", ()):
        label, minimum, maximum, input_rate, cached_input_rate, output_rate = tier_data
        price.tiers.append(
            ModelPriceTier(
                min_input_tokens=minimum,
                max_input_tokens=maximum,
                input_usd_per_million=_seed_decimal(input_rate),
                cached_input_usd_per_million=_seed_optional_decimal(cached_input_rate),
                output_usd_per_million=_seed_decimal(output_rate),
                label=label,
                source_url=price.source_url,
                checked_at=price.checked_at,
                release_date=price.release_date,
                notes=price.notes,
            )
        )


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None and ended_at.tzinfo is not None:
        ended_at = ended_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and ended_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((ended_at - started_at).total_seconds() * 1000))
