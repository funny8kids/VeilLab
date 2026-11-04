from __future__ import annotations

import threading
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

_INIT_LOCK = threading.Lock()


class Base(DeclarativeBase):
    pass


class Database:
    """Small SQLAlchemy wrapper used by the app factory and tests."""

    def __init__(self, url: str) -> None:
        self.url = url
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_on_connect)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    def create_all(self) -> None:
        # Importing here keeps Base metadata populated without import cycles.
        from . import models  # noqa: F401

        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            self._install_sqlite_guards()

    def _install_sqlite_guards(self) -> None:
        """Make the audit table append-only at the database layer too."""

        statements = (
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END
            """,
        )
        with self.engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)

    def session(self) -> Session:
        return self._session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def ensure_database(app: FastAPI) -> Database:
    """Create/seed the app database once.

    This normally runs in the lifespan handler, but it is also safe to call from
    a request dependency so simple ``TestClient(app)`` usage (without entering
    the lifespan context) still works.
    """

    existing = getattr(app.state, "db", None)
    if existing is not None:
        return existing
    with _INIT_LOCK:
        existing = getattr(app.state, "db", None)
        if existing is not None:
            return existing
        from .seed import seed_database

        settings = app.state.settings
        database = Database(settings.database_url)
        database.create_all()
        with database.session() as session:
            seed_database(session, settings)
            session.commit()
        app.state.db = database
        return database


def session_scope(database: Database) -> Iterator[Session]:
    session = database.session()
    try:
        yield session
    finally:
        session.close()
