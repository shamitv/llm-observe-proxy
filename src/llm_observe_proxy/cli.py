from __future__ import annotations

import argparse
import os

import uvicorn

from llm_observe_proxy.config import EXPOSED_INCOMING_HOST, Settings, get_settings
from llm_observe_proxy.database import (
    create_db_engine,
    create_session_factory,
    get_incoming_host,
    get_incoming_port,
    init_db,
    session_scope,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LLM Observe Proxy server.")
    parser.add_argument("--host", help="Bind host. Defaults to the saved setting or localhost.")
    parser.add_argument(
        "--port",
        type=int,
        help="Bind port. Defaults to the saved setting or 8080.",
    )
    parser.add_argument(
        "--expose-all-ips",
        action="store_true",
        help="Bind to 0.0.0.0 instead of localhost.",
    )
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload.")
    parser.add_argument("--database-url", help="SQLite SQLAlchemy URL.")
    parser.add_argument("--upstream-url", help="Default upstream /v1 URL.")
    parser.add_argument("--models-file", help="JSON file containing configured model routes.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.database_url:
        os.environ["LLM_OBSERVE_DATABASE_URL"] = args.database_url
    if args.upstream_url:
        os.environ["LLM_OBSERVE_UPSTREAM_URL"] = args.upstream_url
    if args.models_file:
        os.environ["LLM_OBSERVE_MODELS_FILE"] = args.models_file

    settings = get_settings()
    host, port = resolve_bind(args.host, args.port, args.expose_all_ips, settings)
    uvicorn.run(
        "llm_observe_proxy.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


def resolve_bind(
    host_arg: str | None,
    port_arg: int | None,
    expose_all_ips_arg: bool,
    settings: Settings,
) -> tuple[str, int]:
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            saved_port = get_incoming_port(session, settings)
            saved_host = get_incoming_host(session, settings)
    finally:
        engine.dispose()

    if expose_all_ips_arg:
        host = EXPOSED_INCOMING_HOST
    elif host_arg:
        host = host_arg
    else:
        host = saved_host

    return host, port_arg or saved_port
