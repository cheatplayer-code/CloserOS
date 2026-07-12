"""Async SQLAlchemy database foundation for persistence subsystems.

This module never opens a connection and never reads the environment at import
time. Callers pass a database URL explicitly, or read it from the environment
through :func:`database_url_from_env` at call time.

The canonical driver is psycopg 3, exposed to SQLAlchemy as ``postgresql+psycopg``.
Both the synchronous engine (used by Alembic migrations) and the asynchronous
engine (used by repositories) share the same driver.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as sqlalchemy_create_async_engine,
)

_PSYCOPG_DRIVER = "postgresql+psycopg"


class DatabaseConfigurationError(RuntimeError):
    """Raised when a database URL is missing or unsupported."""


def normalize_database_url(url: str) -> str:
    """Normalize a PostgreSQL URL to the psycopg 3 driver.

    Accepts ``postgres://``, ``postgresql://`` and ``postgresql+<driver>://``
    forms and returns a URL using the ``postgresql+psycopg`` driver. SQLite and
    other non-PostgreSQL URLs are rejected: this subsystem is PostgreSQL-only.
    """

    if not isinstance(url, str) or not url:
        raise DatabaseConfigurationError("database URL must be a non-empty string")

    scheme, separator, remainder = url.partition("://")
    if not separator:
        raise DatabaseConfigurationError("database URL must include a scheme")

    base_scheme = scheme.split("+", maxsplit=1)[0]
    if base_scheme not in {"postgres", "postgresql"}:
        raise DatabaseConfigurationError("only PostgreSQL database URLs are supported")

    return f"{_PSYCOPG_DRIVER}://{remainder}"


def database_url_from_env(variable_name: str = "DATABASE_URL") -> str:
    """Read and normalize a database URL from the environment at call time."""

    raw_url = os.environ.get(variable_name)
    if not raw_url:
        raise DatabaseConfigurationError(f"{variable_name} is not set")

    return normalize_database_url(raw_url)


def create_async_engine(url: str) -> AsyncEngine:
    """Create an async engine for repository access."""

    return sqlalchemy_create_async_engine(normalize_database_url(url), future=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""

    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


def create_authentication_engine(url: str) -> AsyncEngine:
    """Backward-compatible alias for :func:`create_async_engine`."""

    return create_async_engine(url)


def create_authentication_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Backward-compatible alias for :func:`create_session_factory`."""

    return create_session_factory(engine)


def create_migration_engine(url: str) -> Engine:
    """Create a synchronous engine for Alembic migrations."""

    return create_engine(normalize_database_url(url), future=True)
