"""Database configuration and request-scoped transaction management."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_database_url(value: str | URL | None = None) -> URL:
    """Resolve relative SQLite paths against the project, never the caller's cwd."""
    url = make_url(value if value is not None else settings.database_url)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        path = Path(url.database)
        if not path.is_absolute():
            url = url.set(database=(PROJECT_ROOT / path).resolve().as_posix())
    return url


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    # PRAGMA must run outside a transaction, including on Python 3.12+ drivers.
    autocommit = getattr(dbapi_connection, "autocommit", None)
    if autocommit is not None:
        dbapi_connection.autocommit = True
    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        if autocommit is not None:
            dbapi_connection.autocommit = autocommit


def create_db_engine(url: str | URL | None = None, **kwargs) -> Engine:
    """Create an engine with referential integrity enabled for SQLite."""
    engine = create_engine(get_database_url(url), **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Initialize the engine lazily so health/docs do not require a database."""
    return sessionmaker(bind=create_db_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Commit successful requests, roll back failures, and always close the session.

    API consumers must use Depends(get_db, scope="function") so commit failures
    propagate before the HTTP response is sent.
    """
    with get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
