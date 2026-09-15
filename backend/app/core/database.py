"""Async SQLAlchemy engine and session management.

The models use dialect-portable column types so the same schema runs on
PostgreSQL (production) and SQLite (local development and tests).
"""

import ssl
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import certifi
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()


def _strip_libpq_only_query_params(url: str) -> tuple[str, bool]:
    """asyncpg does not understand libpq-style query params (sslmode, channel_binding) —
    it errors with "unexpected keyword argument" if they reach its connect() call. Strip
    them and translate the SSL intent into asyncpg's own `ssl` connect arg instead.
    Returns (cleaned_url, want_ssl).
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sslmode = (params.pop("sslmode", [None])[0] or "").lower()
    params.pop("channel_binding", None)
    want_ssl = sslmode in ("require", "verify-ca", "verify-full", "prefer", "allow")
    cleaned = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
    return cleaned, want_ssl


def _build_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        engine = create_async_engine(url, echo=settings.DEBUG, **kwargs)

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    connect_args: dict = {}
    if "asyncpg" in url:
        # Disable asyncpg's prepared-statement cache: PgBouncer in transaction-pooling
        # mode (used by Neon/Supabase pooled connection strings) does not support
        # prepared statements shared across pooled connections, which otherwise
        # surfaces as random "prepared statement already exists" errors under load.
        connect_args["statement_cache_size"] = 0
        url, want_ssl = _strip_libpq_only_query_params(url)
        if want_ssl:
            # Use certifi's CA bundle explicitly rather than the OS default: some Python
            # installs (notably python.org's macOS build) don't wire up a usable system
            # trust store, which otherwise fails with "unable to get local issuer
            # certificate" even though the server's certificate is perfectly valid.
            connect_args["ssl"] = ssl.create_default_context(cafile=certifi.where())
    return create_async_engine(
        url,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine(settings.async_database_url)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db_for_dev() -> None:
    """Create tables directly (SQLite dev only). Production uses Alembic."""
    from app import models  # noqa: F401 - register models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
