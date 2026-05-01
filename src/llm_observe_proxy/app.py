from __future__ import annotations

from fastapi import FastAPI

from llm_observe_proxy.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="LLM Observe Proxy",
        summary="OpenAI-compatible LLM proxy with SQLite observability.",
        version="0.1.0",
    )
    app.state.settings = resolved_settings

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
