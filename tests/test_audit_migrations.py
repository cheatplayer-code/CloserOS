"""PostgreSQL migration tests for the audit_events schema."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid

import psycopg
import pytest
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
    assert script.get_current_head() == "8e4b1d0f6a23"


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


def test_audit_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "audit_events" not in table_names
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            upgraded = inspect(engine).get_table_names()
        finally:
            engine.dispose()
        assert "audit_events" in upgraded
    finally:
        _drop_database(admin_url, database_name)


def test_audit_database_trigger_rejects_update() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    event_id = uuid.uuid4()
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
                    id, scope, tenant_id, actor_type, actor_id, action,
                    target_type, target_id, occurred_at, correlation_id, metadata
                ) VALUES (
                    %s, 'global', NULL, 'anonymous', NULL, 'auth.login.failed',
                    'authentication', NULL, TIMESTAMPTZ '2026-07-12T10:00:00Z',
                    %s, '{"outcome":"failure","reason_code":"invalid_credentials"}'::jsonb
                )
                """,
                (event_id, correlation_id),
            )
            connection.commit()
            with pytest.raises(psycopg.errors.RaiseException):
                connection.execute(
                    "UPDATE audit_events SET action = %s WHERE id = %s",
                    ("auth.login.succeeded", event_id),
                )
    finally:
        _drop_database(admin_url, database_name)
