"""
src/persistence/db.py
=====================
Async SQLAlchemy engine bootstrap for the Mekka Trading SQLite store.

Engine and sessionmaker are module-level singletons created lazily on
first call to `init_engine()`. Tables are created automatically the
first time the engine is initialised — no Alembic for now.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings
from src.persistence.models import Base


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _resolve_db_url() -> str:
    """
    Resolve the SQLite URL.

    settings.sqlite_db_path is a relative or absolute path. We turn it
    into an aiosqlite URL with the database directory pre-created.
    """
    raw = settings.sqlite_db_path
    path = Path(raw).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


async def init_engine() -> AsyncEngine:
    """
    Initialise the engine and create tables on first call. Idempotent.
    Returns the singleton engine.
    """
    global _engine, _sessionmaker

    if _engine is not None:
        return _engine

    url = _resolve_db_url()
    _engine = create_async_engine(
        url,
        echo=False,
        future=True,
        # aiosqlite serializes writes to the event loop — pool_size is 1
        pool_pre_ping=True,
    )

    # WAL mode: allows concurrent reads while a write is in progress.
    # Critical for production: dashboard (reads) + NickFury (writes) run in
    # separate processes and share the same SQLite file. Without WAL the
    # default DELETE journal causes OperationalError: database is locked.
    @event.listens_for(_engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")   # safe with WAL
        cursor.execute("PRAGMA foreign_keys=ON")       # enforce FK integrity
        cursor.execute("PRAGMA busy_timeout=5000")     # wait 5s on lock instead of fail
        cursor.close()

    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Async context manager that yields a fresh AsyncSession.

    Usage:
        async with get_session() as session:
            session.add(record)
            await session.commit()
    """
    if _sessionmaker is None:
        await init_engine()
    assert _sessionmaker is not None  # mypy
    async with _sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose() -> None:
    """Dispose of the global engine (used in tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


def reset_db_path(path: str) -> None:
    """
    Override the SQLite path for tests. Must be called before init_engine
    or after dispose().
    """
    os.environ["SQLITE_DB_PATH"] = path
    # Pydantic Settings does not auto-rebuild — caller is expected to
    # reload settings or pass a fresh path via fixtures.
