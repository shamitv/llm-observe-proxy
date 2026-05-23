from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
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
    ModelRoute,
    Settings,
    normalize_provider_slug,
    normalize_provider_url,
    parse_model_routes,
)

MODEL_ROUTES_SETTING_KEY = "model_routes_json"
DEFAULT_COMPAT_FIXES_SETTING_KEY = "default_compat_fixes_json"
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
        "slug": "openai",
        "name": "OpenAI",
        "upstream_url": "https://api.openai.com/v1",
        "currency": "USD",
    },
    {
        "slug": "anthropic",
        "name": "Anthropic",
        "upstream_url": "https://api.anthropic.com/v1",
        "currency": "USD",
    },
    {
        "slug": "google",
        "name": "Google Gemini",
        "upstream_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "currency": "USD",
    },
    {
        "slug": "alibaba",
        "name": "Alibaba Cloud Model Studio",
        "upstream_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "currency": "USD",
    },
    {
        "slug": "deepseek",
        "name": "DeepSeek",
        "upstream_url": "https://api.deepseek.com/v1",
        "currency": "USD",
    },
    {
        "slug": "zai",
        "name": "Z.ai",
        "upstream_url": "https://api.z.ai/api/paas/v4",
        "currency": "USD",
    },
    {
        "slug": "moonshot",
        "name": "Moonshot Kimi",
        "upstream_url": "https://api.moonshot.ai/v1",
        "currency": "USD",
    },
    {
        "slug": "mistral",
        "name": "Mistral AI",
        "upstream_url": "https://api.mistral.ai/v1",
        "currency": "USD",
    },
    {
        "slug": "openrouter",
        "name": "OpenRouter",
        "upstream_url": "https://openrouter.ai/api/v1",
        "currency": "USD",
    },
    {
        "slug": "huggingface-router",
        "name": "Hugging Face Router",
        "upstream_url": "https://router.huggingface.co/v1",
        "currency": "USD",
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

DEFAULT_MODEL_PRICE_REVISIONS = {
    (str(price["provider_slug"]), str(price["model"])): price
    for price in _LEGACY_SCALAR_SEED_MODEL_PRICES
}


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
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    requests: Mapped[list[RequestRecord]] = relationship(back_populates="task_run")


class RequestRecord(Base):
    __tablename__ = "request_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
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
    _ensure_sqlite_request_record_schema(engine)
    _ensure_sqlite_model_price_schema(engine)
    seed_default_model_pricing(engine)


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


def list_model_providers(session: Session) -> list[ModelProvider]:
    return list(session.scalars(select(ModelProvider).order_by(ModelProvider.name)).all())


def list_model_prices(session: Session) -> list[ModelPrice]:
    return list(
        session.scalars(
            select(ModelPrice)
            .join(ModelProvider)
            .options(contains_eager(ModelPrice.provider), selectinload(ModelPrice.tiers))
            .order_by(ModelProvider.name, ModelPrice.model)
        ).all()
    )


def upsert_model_provider(
    session: Session,
    *,
    slug: str,
    name: str,
    upstream_url: str = "",
    currency: str = "USD",
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


def seed_default_model_pricing(engine: Engine) -> None:
    with Session(engine) as session:
        for provider_data in DEFAULT_MODEL_PROVIDERS:
            if session.get(ModelProvider, provider_data["slug"]) is None:
                session.add(ModelProvider(**provider_data))
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
                previous_seed = DEFAULT_MODEL_PRICE_REVISIONS.get((provider_slug, model))
                if previous_seed is not None and _model_price_matches_seed(
                    existing,
                    previous_seed,
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
    value = get_setting(session, MODEL_ROUTES_SETTING_KEY)
    if not value:
        return ()
    try:
        routes = parse_model_routes(json.loads(value))
    except (json.JSONDecodeError, ValueError):
        return ()
    return tuple(
        ModelRoute(
            model=route.model,
            upstream_url=route.upstream_url,
            upstream_model=route.upstream_model,
            provider_slug=route.provider_slug,
            api_key_env=route.api_key_env,
            fixes=route.fixes,
        )
        for route in routes
    )


def get_effective_model_routes(session: Session, settings: Settings) -> tuple[ModelRoute, ...]:
    return (*settings.model_routes, *get_ui_model_routes(session))


def upsert_ui_model_route(session: Session, settings: Settings, route: ModelRoute) -> None:
    if route.model in {configured.model for configured in settings.model_routes}:
        raise ValueError("Model route already exists in startup configuration.")

    routes = [
        existing for existing in get_ui_model_routes(session) if existing.model != route.model
    ]
    routes.append(route)
    _set_ui_model_routes(session, routes)


def delete_ui_model_route(session: Session, model: str) -> bool:
    resolved_model = model.strip()
    routes = list(get_ui_model_routes(session))
    remaining = [route for route in routes if route.model != resolved_model]
    if len(remaining) == len(routes):
        return False
    _set_ui_model_routes(session, remaining)
    return True


def get_active_task_run(session: Session) -> TaskRun | None:
    return session.scalar(
        select(TaskRun).where(TaskRun.ended_at.is_(None)).order_by(TaskRun.started_at.desc())
    )


def start_task_run(session: Session, name: str, notes: str | None = None) -> TaskRun:
    resolved_name = name.strip()
    if not resolved_name:
        raise ValueError("Run name is required.")

    now = _now()
    active_runs = session.scalars(select(TaskRun).where(TaskRun.ended_at.is_(None))).all()
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
