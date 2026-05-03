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
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from llm_observe_proxy.config import (
    EXPOSED_INCOMING_HOST,
    ModelRoute,
    Settings,
    normalize_provider_slug,
    normalize_provider_url,
    parse_model_routes,
)

MODEL_ROUTES_SETTING_KEY = "model_routes_json"
DEFAULT_PRICING_SOURCE = "Seeded from official standard paid text pricing checked on 2026-05-03."
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
)
DEFAULT_MODEL_PRICES = (
    ("openai", "gpt-5.5", "GPT-5.5", "5.00", "30.00"),
    ("openai", "gpt-5.5-pro", "GPT-5.5 Pro", "30.00", "180.00"),
    ("openai", "gpt-5.4", "GPT-5.4", "2.50", "15.00"),
    ("openai", "gpt-5.4-mini", "GPT-5.4 Mini", "0.75", "4.50"),
    ("openai", "gpt-5.4-nano", "GPT-5.4 Nano", "0.20", "1.25"),
    ("openai", "gpt-5.4-pro", "GPT-5.4 Pro", "30.00", "180.00"),
    ("anthropic", "claude-opus-4-7", "Claude Opus 4.7", "5.00", "25.00"),
    ("anthropic", "claude-opus-4-6", "Claude Opus 4.6", "5.00", "25.00"),
    ("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6", "3.00", "15.00"),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5", "1.00", "5.00"),
    ("google", "gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", "2.00", "12.00"),
    ("google", "gemini-3-flash-preview", "Gemini 3 Flash Preview", "0.50", "3.00"),
    ("google", "gemini-2.5-pro", "Gemini 2.5 Pro", "1.25", "10.00"),
    ("google", "gemini-2.5-flash", "Gemini 2.5 Flash", "0.30", "2.50"),
    ("google", "gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "0.10", "0.40"),
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
    output_usd_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
    )

    provider: Mapped[ModelProvider] = relationship(back_populates="prices")


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


def list_model_providers(session: Session) -> list[ModelProvider]:
    return list(session.scalars(select(ModelProvider).order_by(ModelProvider.name)).all())


def list_model_prices(session: Session) -> list[ModelPrice]:
    return list(
        session.scalars(
            select(ModelPrice)
            .join(ModelProvider)
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
    aliases: str | list[str] | tuple[str, ...] = "",
    display_name: str = "",
    active: bool = True,
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
    price.output_usd_per_million = output_rate
    price.active = active
    price.notes = notes.strip() or None
    session.flush()
    return price


def delete_model_price(session: Session, provider_slug: str, model: str) -> bool:
    resolved_provider_slug = normalize_provider_slug(provider_slug)
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

        for provider_slug, model, display_name, input_rate, output_rate in DEFAULT_MODEL_PRICES:
            existing = session.scalar(
                select(ModelPrice).where(
                    ModelPrice.provider_slug == provider_slug,
                    ModelPrice.model == model,
                )
            )
            if existing is not None:
                continue
            session.add(
                ModelPrice(
                    provider_slug=provider_slug,
                    model=model,
                    display_name=display_name,
                    input_usd_per_million=Decimal(input_rate),
                    output_usd_per_million=Decimal(output_rate),
                    active=True,
                    notes=DEFAULT_PRICING_SOURCE,
                )
            )
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
    records = session.scalars(
        select(RequestRecord)
        .where(RequestRecord.task_run_id == task_run_id)
        .order_by(RequestRecord.created_at)
    ).all()
    completed_times = [record.completed_at for record in records if record.completed_at is not None]
    first_request_at = records[0].created_at if records else None
    last_completed_at = max(completed_times) if completed_times else None
    total_request_duration_ms = sum(record.duration_ms or 0 for record in records)
    return {
        "request_count": len(records),
        "first_request_at": first_request_at,
        "last_completed_at": last_completed_at,
        "llm_wall_time_ms": _duration_ms(first_request_at, last_completed_at),
        "total_request_duration_ms": total_request_duration_ms,
        "streams": sum(1 for record in records if record.is_stream),
        "images": sum(1 for record in records if record.has_images),
        "tools": sum(1 for record in records if record.has_tool_calls),
        "errors": sum(1 for record in records if record.error),
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


def _set_ui_model_routes(session: Session, routes: list[ModelRoute]) -> None:
    payload = [
        {
            "model": route.model,
            "upstream_url": route.upstream_url,
            **({"upstream_model": route.upstream_model} if route.upstream_model else {}),
            **({"provider_slug": route.provider_slug} if route.provider_slug else {}),
            **({"api_key_env": route.api_key_env} if route.api_key_env else {}),
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


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None and ended_at.tzinfo is not None:
        ended_at = ended_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and ended_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((ended_at - started_at).total_seconds() * 1000))
