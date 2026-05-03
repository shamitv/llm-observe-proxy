from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
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

from llm_observe_proxy.config import EXPOSED_INCOMING_HOST, ModelRoute, Settings, parse_model_routes

MODEL_ROUTES_SETTING_KEY = "model_routes_json"


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


def _set_ui_model_routes(session: Session, routes: list[ModelRoute]) -> None:
    payload = [
        {
            "model": route.model,
            "upstream_url": route.upstream_url,
            **({"upstream_model": route.upstream_model} if route.upstream_model else {}),
            **({"api_key_env": route.api_key_env} if route.api_key_env else {}),
        }
        for route in routes
    ]
    set_setting(session, MODEL_ROUTES_SETTING_KEY, json.dumps(payload, separators=(",", ":")))


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None and ended_at.tzinfo is not None:
        ended_at = ended_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and ended_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((ended_at - started_at).total_seconds() * 1000))
