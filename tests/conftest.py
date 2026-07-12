"""Shared PostgreSQL fixtures for authentication persistence integration tests.

These fixtures create an isolated temporary database on the existing local
PostgreSQL instance, run Alembic migrations, and drop the database after the
test module completes. The main ``closeros_local`` database and its volume are
never modified.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from alembic import command
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from sqlalchemy.ext.asyncio import AsyncEngine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "auth_persistence: PostgreSQL authentication persistence integration tests",
    )


_DEFAULT_ADMIN_URL = (
    "postgresql://closeros_local:closeros_local_only_change_me@127.0.0.1:5432/postgres"
)


def _admin_database_url() -> str:
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        normalized = normalize_database_url(test_url)
        scheme, _, remainder = normalized.partition("://")
        credentials_and_host, _, _database = remainder.rpartition("/")
        return f"{scheme}://{credentials_and_host}/postgres"

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        normalized = normalize_database_url(database_url)
        scheme, _, remainder = normalized.partition("://")
        credentials_and_host, _, _database = remainder.rpartition("/")
        return f"{scheme}://{credentials_and_host}/postgres"

    return _DEFAULT_ADMIN_URL


def _database_name_prefix() -> str:
    return "closeros_auth_test_"


def _create_database(admin_url: str, database_name: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(database_name))
        )


def _drop_database(admin_url: str, database_name: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        connection.execute(
            psycopg.sql.SQL("DROP DATABASE IF EXISTS {}").format(
                psycopg.sql.Identifier(database_name)
            )
        )


def _run_migrations(database_url: str) -> None:
    config = build_alembic_config(database_url)
    command.upgrade(config, "head")


def _run_downgrade(database_url: str) -> None:
    config = build_alembic_config(database_url)
    command.downgrade(config, "base")


@pytest.fixture(scope="module")
def auth_test_database_url() -> Iterator[str]:
    admin_url = _admin_database_url()
    database_name = f"{_database_name_prefix()}{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)

    scheme, _, remainder = normalize_database_url(admin_url).partition("://")
    credentials_and_host, _, _ = remainder.rpartition("/")
    database_url = f"{scheme}://{credentials_and_host}/{database_name}"

    try:
        _run_migrations(database_url)
        yield database_url
    finally:
        _drop_database(admin_url, database_name)


@pytest.fixture(scope="module")
def auth_async_engine(auth_test_database_url: str) -> Iterator[AsyncEngine]:
    engine = create_authentication_engine(auth_test_database_url)

    async def dispose() -> None:
        await engine.dispose()

    yield engine
    asyncio.run(dispose())


@pytest.fixture
def auth_session_factory(auth_async_engine: AsyncEngine) -> Any:
    return create_authentication_sessionmaker(auth_async_engine)


@pytest.fixture
def auth_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.authentication_unit_of_work import (
        SqlAlchemyAuthenticationUnitOfWork,
    )

    def factory() -> SqlAlchemyAuthenticationUnitOfWork:
        return SqlAlchemyAuthenticationUnitOfWork(auth_session_factory)

    return factory


@pytest.fixture(autouse=True)
def _reset_auth_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("auth_persistence") is None:
        yield
        return

    from sqlalchemy import text

    engine: AsyncEngine = request.getfixturevalue("auth_async_engine")

    async def reset() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE authentication_one_time_tokens, "
                    "authentication_sessions, authentication_credentials, "
                    "users RESTART IDENTITY CASCADE"
                )
            )

    asyncio.run(reset())
    yield
    asyncio.run(reset())
