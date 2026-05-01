from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "sqlite:///./llm_observe_proxy.sqlite3"
DEFAULT_INCOMING_HOST = "localhost"
DEFAULT_INCOMING_PORT = 8080
DEFAULT_UPSTREAM_URL = "http://localhost:8000/v1"
EXPOSED_INCOMING_HOST = "0.0.0.0"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    incoming_host: str = DEFAULT_INCOMING_HOST
    incoming_port: int = DEFAULT_INCOMING_PORT
    expose_all_ips: bool = False
    upstream_url: str = DEFAULT_UPSTREAM_URL
    log_level: str = "INFO"


def get_settings(
    *,
    database_url: str | None = None,
    incoming_host: str | None = None,
    incoming_port: int | None = None,
    expose_all_ips: bool | None = None,
    upstream_url: str | None = None,
    log_level: str | None = None,
) -> Settings:
    return Settings(
        database_url=database_url or os.getenv("LLM_OBSERVE_DATABASE_URL", DEFAULT_DATABASE_URL),
        incoming_host=incoming_host
        or os.getenv("LLM_OBSERVE_INCOMING_HOST", DEFAULT_INCOMING_HOST),
        incoming_port=incoming_port
        or _env_int("LLM_OBSERVE_INCOMING_PORT", DEFAULT_INCOMING_PORT),
        expose_all_ips=(
            expose_all_ips
            if expose_all_ips is not None
            else _env_bool("LLM_OBSERVE_EXPOSE_ALL_IPS", False)
        ),
        upstream_url=upstream_url or os.getenv("LLM_OBSERVE_UPSTREAM_URL", DEFAULT_UPSTREAM_URL),
        log_level=log_level or os.getenv("LLM_OBSERVE_LOG_LEVEL", "INFO"),
    )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
