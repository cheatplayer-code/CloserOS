"""Shared PostgreSQL fixtures for authentication persistence integration tests.

These fixtures create an isolated temporary database on the existing local
PostgreSQL instance, run Alembic migrations, and drop the database after the
test module completes. The main ``closeros_local`` database and its volume are
never modified.
"""

# mypy: disable-error-code=import-untyped

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
)
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "auth_persistence: PostgreSQL authentication persistence integration tests",
    )
    config.addinivalue_line(
        "markers",
        "platform_persistence: PostgreSQL platform and canonical persistence integration tests",
    )
    config.addinivalue_line(
        "markers",
        "hi_persistence: PostgreSQL encrypted content and outbox integration tests",
    )
    config.addinivalue_line(
        "markers",
        "jk_persistence: PostgreSQL webhook and CSV import ingestion integration tests",
    )
    config.addinivalue_line(
        "markers",
        "lm_persistence: PostgreSQL content redaction and metrics integration tests",
    )
    config.addinivalue_line(
        "markers",
        "nopq_persistence: PostgreSQL NOPQ AI and knowledge integration tests",
    )
    config.addinivalue_line(
        "markers",
        "redis_integration: Redis stream queue integration tests",
    )
    config.addinivalue_line(
        "markers",
        "rstu_persistence: PostgreSQL RSTU product workspace integration tests",
    )
    config.addinivalue_line(
        "markers",
        "vw_persistence: PostgreSQL WhatsApp Cloud provider integration tests",
    )


_PLATFORM_TRUNCATE_TABLES = (
    "conversation_finding_knowledge_citations",
    "follow_up_tasks",
    "conversation_finding_evidence",
    "conversation_findings",
    "conversation_analysis_runs",
    "knowledge_chunk_terms",
    "knowledge_chunks",
    "knowledge_document_versions",
    "knowledge_documents",
    "ai_usage_daily",
    "tenant_ai_policies",
    "metric_values",
    "metric_snapshots",
    "content_sanitization_category_counts",
    "content_sanitizations",
    "csv_import_row_errors",
    "csv_import_batches",
    "webhook_events",
    "outbox_job_attempts",
    "outbox_jobs",
    "encrypted_contents",
    "crm_outcomes",
    "manager_assignments",
    "message_delivery_status_events",
    "message_deletion_events",
    "message_edit_events",
    "messages",
    "conversation_threads",
    "sales_cases",
    "leads",
    "channel_connections",
    "whatsapp_cloud_connections",
    "provider_message_templates",
    "provider_media_references",
    "outbound_messages",
    "outbound_delivery_attempts",
    "invitation_roles",
    "invitations",
    "membership_roles",
    "memberships",
    "tenants",
    "audit_events",
    "authentication_one_time_tokens",
    "authentication_sessions",
    "authentication_credentials",
    "users",
)


# Direct psycopg driver (no SQLAlchemy dialect suffix) for `psycopg.connect`.
_DIRECT_DRIVER = "postgresql"
# SQLAlchemy dialect driver used by engines and Alembic.
_SQLALCHEMY_DRIVER = "postgresql+psycopg"
_MAINTENANCE_DATABASE = "postgres"

_DEFAULT_ADMIN_URL = (
    "postgresql://closeros_local:closeros_local_only_change_me@127.0.0.1:5432/postgres"
)


def _rebuild_database_url(url: str, *, database: str, sqlalchemy: bool) -> str:
    """Return a PostgreSQL URL with a chosen database name and driver.

    Parsing and rendering go through SQLAlchemy's ``URL`` so credentials, host,
    port, and query parameters are preserved without fragile string surgery.
    When ``sqlalchemy`` is ``True`` the SQLAlchemy ``postgresql+psycopg`` driver
    is used; otherwise a direct ``postgresql`` URI suitable for
    ``psycopg.connect`` is produced.
    """

    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("only PostgreSQL database URLs are supported")

    drivername = _SQLALCHEMY_DRIVER if sqlalchemy else _DIRECT_DRIVER
    rebuilt = parsed.set(drivername=drivername, database=database)
    return rebuilt.render_as_string(hide_password=False)


def _admin_database_url() -> str:
    """Return a direct psycopg admin URI targeting the maintenance database."""

    source_url = (
        os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or _DEFAULT_ADMIN_URL
    )
    return _rebuild_database_url(
        source_url,
        database=_MAINTENANCE_DATABASE,
        sqlalchemy=False,
    )


def _sqlalchemy_database_url(admin_url: str, database_name: str) -> str:
    """Return a SQLAlchemy ``postgresql+psycopg`` URL for a temporary database."""

    return _rebuild_database_url(admin_url, database=database_name, sqlalchemy=True)


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

    database_url = _sqlalchemy_database_url(admin_url, database_name)

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


@pytest.fixture
def auth_audit_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork

    def factory() -> SqlAlchemyAuditUnitOfWork:
        return SqlAlchemyAuditUnitOfWork(auth_session_factory)

    return factory


@pytest.fixture
def platform_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork

    def factory() -> SqlAlchemyPlatformUnitOfWork:
        return SqlAlchemyPlatformUnitOfWork(auth_session_factory)

    return factory


@pytest.fixture
def tenant_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork

    def factory() -> SqlAlchemyTenantUnitOfWork:
        return SqlAlchemyTenantUnitOfWork(auth_session_factory)

    return factory


@pytest.fixture
def canonical_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.canonical_unit_of_work import SqlAlchemyCanonicalUnitOfWork

    def factory() -> SqlAlchemyCanonicalUnitOfWork:
        return SqlAlchemyCanonicalUnitOfWork(auth_session_factory)

    return factory


@pytest.fixture
def integrated_uow_factory(auth_session_factory: Any) -> Any:
    from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

    def factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(auth_session_factory)

    return factory


def _requires_persistence_reset(request: pytest.FixtureRequest) -> bool:
    return (
        request.node.get_closest_marker("auth_persistence") is not None
        or request.node.get_closest_marker("platform_persistence") is not None
        or request.node.get_closest_marker("hi_persistence") is not None
        or request.node.get_closest_marker("jk_persistence") is not None
        or request.node.get_closest_marker("lm_persistence") is not None
        or request.node.get_closest_marker("nopq_persistence") is not None
        or request.node.get_closest_marker("rstu_persistence") is not None
        or request.node.get_closest_marker("vw_persistence") is not None
    )


@pytest.fixture(autouse=True)
def _reset_auth_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    if not _requires_persistence_reset(request):
        yield
        return

    from sqlalchemy import text

    engine: AsyncEngine = request.getfixturevalue("auth_async_engine")
    truncate_sql = f"TRUNCATE {', '.join(_PLATFORM_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"

    async def reset() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(truncate_sql))

    asyncio.run(reset())
    yield
    asyncio.run(reset())
