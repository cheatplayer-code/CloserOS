"""PostgreSQL migration tests for platform and canonical schema."""

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
    database_name = f"closeros_platform_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)

    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_platform_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "f2a8c4e6b1d3"


def test_platform_migration_upgrade_creates_platform_tables() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        assert {
            "tenants",
            "memberships",
            "membership_roles",
            "invitations",
            "invitation_roles",
            "channel_connections",
            "conversation_threads",
            "messages",
            "webhook_events",
        }.issubset(table_names)
    finally:
        _drop_database(admin_url, database_name)


def test_platform_migration_downgrade_and_reupgrade() -> None:
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

        assert "tenants" not in table_names
        assert "messages" not in table_names

        command.upgrade(config, "head")

        engine = create_migration_engine(database_url)
        try:
            upgraded_table_names = inspect(engine).get_table_names()
        finally:
            engine.dispose()

        assert "channel_connections" in upgraded_table_names
    finally:
        _drop_database(admin_url, database_name)


def test_cross_tenant_composite_foreign_key_rejects_mismatched_tenant() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    connection_a = uuid.uuid4()
    thread_b = uuid.uuid4()

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
                INSERT INTO tenants (
                    id, name, status, time_zone,
                    raw_message_days, sanitized_message_days, ai_output_days,
                    audit_log_days, backup_days, post_contract_deletion_days
                ) VALUES
                    (%s, %s, %s, %s, 30, 30, 30, 365, 30, 90),
                    (%s, %s, %s, %s, 30, 30, 30, 365, 30, 90)
                """,
                (
                    tenant_a,
                    "Tenant A",
                    "active",
                    "UTC",
                    tenant_b,
                    "Tenant B",
                    "active",
                    "UTC",
                ),
            )
            connection.execute(
                """
                INSERT INTO channel_connections (
                    id, tenant_id, provider, external_connection_id, status,
                    adapter_metadata, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb,
                    TIMESTAMPTZ '2026-07-12T09:00:00Z',
                    TIMESTAMPTZ '2026-07-12T09:00:00Z'
                )
                """,
                (
                    connection_a,
                    tenant_a,
                    "whatsapp",
                    "wa-cross-tenant-test",
                    "active",
                    '{"provider_ref": "synthetic"}',
                ),
            )
            connection.commit()

            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    """
                    INSERT INTO conversation_threads (
                        id, tenant_id, channel_connection_id, external_conversation_id,
                        sales_case_id, lifecycle_status, adapter_metadata,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, NULL, %s, %s::jsonb,
                        TIMESTAMPTZ '2026-07-12T09:00:00Z',
                        TIMESTAMPTZ '2026-07-12T09:00:00Z'
                    )
                    """,
                    (
                        thread_b,
                        tenant_b,
                        connection_a,
                        "thread-cross-tenant-test",
                        "awaiting_customer",
                        '{"provider_ref": "synthetic"}',
                    ),
                )
    finally:
        _drop_database(admin_url, database_name)
