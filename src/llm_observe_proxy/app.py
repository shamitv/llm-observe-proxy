from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from llm_observe_proxy.admin import router as admin_router
from llm_observe_proxy.config import Settings, get_settings
from llm_observe_proxy.database import create_db_engine, create_session_factory, init_db
from llm_observe_proxy.proxy import router as proxy_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(resolved_settings.database_url)
        init_db(engine)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.http_client = httpx.AsyncClient(timeout=None)
        try:
            yield
        finally:
            await app.state.http_client.aclose()
            engine.dispose()

    app = FastAPI(
        title="LLM Observe Proxy",
        summary="OpenAI-compatible LLM proxy with SQLite observability.",
        version="0.1.1",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(proxy_router)
    app.include_router(admin_router)
    app.mount(
        "/admin/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="admin_static",
    )

    return app
