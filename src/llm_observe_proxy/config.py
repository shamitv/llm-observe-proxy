from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_UPSTREAM_URL = "http://localhost:8080/v1"
DEFAULT_DATABASE_URL = "sqlite:///./llm_observe_proxy.sqlite3"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    upstream_url: str = DEFAULT_UPSTREAM_URL
    log_level: str = "INFO"


def get_settings(
    *,
    database_url: str | None = None,
    upstream_url: str | None = None,
    log_level: str | None = None,
) -> Settings:
    return Settings(
        database_url=database_url or os.getenv("LLM_OBSERVE_DATABASE_URL", DEFAULT_DATABASE_URL),
        upstream_url=upstream_url or os.getenv("LLM_OBSERVE_UPSTREAM_URL", DEFAULT_UPSTREAM_URL),
        log_level=log_level or os.getenv("LLM_OBSERVE_LOG_LEVEL", "INFO"),
    )
