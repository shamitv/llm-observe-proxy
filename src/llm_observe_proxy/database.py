from __future__ import annotations

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

from llm_observe_proxy.config import EXPOSED_INCOMING_HOST, Settings


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RequestRecord(Base):
    __tablename__ = "request_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    query_string: Mapped[str] = mapped_column(Text, default="")
    endpoint: Mapped[str] = mapped_column(String(512), index=True)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
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


def _ensure_sqlite_parent(engine: Engine) -> None:
    database = engine.url.database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)

