from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_DATABASE_URL = "sqlite:///./llm_observe_proxy.sqlite3"
DEFAULT_INCOMING_HOST = "localhost"
DEFAULT_INCOMING_PORT = 8080
DEFAULT_UPSTREAM_URL = "http://localhost:8000/v1"
EXPOSED_INCOMING_HOST = "0.0.0.0"


@dataclass(frozen=True)
class ModelRoute:
    model: str
    upstream_url: str
    upstream_model: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None

    def __post_init__(self) -> None:
        model = self.model.strip()
        if not model:
            raise ValueError("Model route model is required.")
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "upstream_url", normalize_upstream_url(self.upstream_url))
        object.__setattr__(self, "upstream_model", _optional_str(self.upstream_model))
        object.__setattr__(self, "api_key", _optional_str(self.api_key))
        object.__setattr__(self, "api_key_env", _optional_str(self.api_key_env))
        if self.api_key and self.api_key_env:
            raise ValueError("Model routes cannot define both api_key and api_key_env.")

    @property
    def effective_upstream_model(self) -> str:
        return self.upstream_model or self.model


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    incoming_host: str = DEFAULT_INCOMING_HOST
    incoming_port: int = DEFAULT_INCOMING_PORT
    expose_all_ips: bool = False
    upstream_url: str = DEFAULT_UPSTREAM_URL
    model_routes: tuple[ModelRoute, ...] = ()
    log_level: str = "INFO"


def get_settings(
    *,
    database_url: str | None = None,
    incoming_host: str | None = None,
    incoming_port: int | None = None,
    expose_all_ips: bool | None = None,
    upstream_url: str | None = None,
    model_routes: tuple[ModelRoute, ...] | None = None,
    models_file: str | None = None,
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
        model_routes=(
            model_routes
            if model_routes is not None
            else load_model_routes(
                models_file=models_file or os.getenv("LLM_OBSERVE_MODELS_FILE"),
                models_json=os.getenv("LLM_OBSERVE_MODELS_JSON"),
            )
        ),
        log_level=log_level or os.getenv("LLM_OBSERVE_LOG_LEVEL", "INFO"),
    )


def normalize_upstream_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Upstream URL must be an absolute http(s) URL.")
    if not normalized.endswith("/v1"):
        raise ValueError("Upstream URL must point to a /v1 base URL.")
    return normalized


def load_model_routes(
    *,
    models_file: str | None = None,
    models_json: str | None = None,
) -> tuple[ModelRoute, ...]:
    if models_file:
        try:
            data = json.loads(Path(models_file).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError("Unable to read LLM_OBSERVE_MODELS_FILE.") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("LLM_OBSERVE_MODELS_FILE must contain valid JSON.") from exc
        return parse_model_routes(data)
    if models_json:
        try:
            data = json.loads(models_json)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM_OBSERVE_MODELS_JSON must contain valid JSON.") from exc
        return parse_model_routes(data)
    return ()


def parse_model_routes(data: Any) -> tuple[ModelRoute, ...]:
    if not isinstance(data, list):
        raise ValueError("Model routes configuration must be a JSON array.")

    routes: list[ModelRoute] = []
    seen: set[str] = set()
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Model route #{index} must be an object.")
        route = _model_route_from_dict(item)
        if route.model in seen:
            raise ValueError(f"Duplicate model route: {route.model}.")
        seen.add(route.model)
        routes.append(route)
    return tuple(routes)


def _model_route_from_dict(item: dict[str, Any]) -> ModelRoute:
    model = item.get("model")
    upstream_url = item.get("upstream_url")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Model route model is required.")
    if not isinstance(upstream_url, str) or not upstream_url.strip():
        raise ValueError("Model route upstream_url is required.")
    return ModelRoute(
        model=model,
        upstream_url=upstream_url,
        upstream_model=(
            item.get("upstream_model") if isinstance(item.get("upstream_model"), str) else None
        ),
        api_key=item.get("api_key") if isinstance(item.get("api_key"), str) else None,
        api_key_env=item.get("api_key_env") if isinstance(item.get("api_key_env"), str) else None,
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


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
