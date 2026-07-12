"""PostgreSQL migration tests for the audit schema."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid

import psycopg
from alembic import command
from alembic.script import ScriptDirectory
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import create_migration_engine
from sqlalchemy import inspect

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _rebuild_database_url,
    _sqlalchemy_database_url,
)


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_audit_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)

    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_audit_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "b3d7f1a4c8e6"


def test_audit_migration_upgrade_creates_audit_events_table() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = inspect(engine).get_table_names()
        finally:
            engine.dispose()

        assert "audit_events" in table_names
    finally:
        _drop_database(admin_url, database_name)


def test_platform_audit_action_constraint_accepts_membership_created() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    event_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    correlation_id = uuid.uuid4()

    try:
        command.upgrade(config, "head")

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    id, scope, tenant_id, actor_type, actor_id,
                    action, target_type, target_id, occurred_at,
                    correlation_id, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    TIMESTAMPTZ '2026-07-12T10:00:00Z',
                    %s, %s::jsonb
                )
                """,
                (
                    event_id,
                    "tenant",
                    tenant_id,
                    "user",
                    actor_id,
                    "membership.created",
                    "membership",
                    target_id,
                    correlation_id,
                    '{"outcome": "success"}',
                ),
            )
            connection.commit()
    finally:
        _drop_database(admin_url, database_name)
