from __future__ import annotations

import argparse
import os

import uvicorn

from llm_observe_proxy.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LLM Observe Proxy server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", default=8000, type=int, help="Bind port.")
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload.")
    parser.add_argument("--database-url", help="SQLite SQLAlchemy URL.")
    parser.add_argument("--upstream-url", help="Default upstream /v1 URL.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.database_url:
        os.environ["LLM_OBSERVE_DATABASE_URL"] = args.database_url
    if args.upstream_url:
        os.environ["LLM_OBSERVE_UPSTREAM_URL"] = args.upstream_url

    settings = get_settings()
    uvicorn.run(
        "llm_observe_proxy.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )
