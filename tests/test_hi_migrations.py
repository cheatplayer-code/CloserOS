"""PostgreSQL migration tests for encrypted content and outbox schema."""

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
    database_name = f"closeros_hi_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_hi_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "e3b7c9d1f5a2"


def test_hi_migration_upgrade_creates_tables() -> None:
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
            "encrypted_contents",
            "outbox_jobs",
            "outbox_job_attempts",
        }.issubset(table_names)
    finally:
        _drop_database(admin_url, database_name)


def test_hi_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "d4e8f1a2b3c5")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "encrypted_contents" not in table_names
        assert "outbox_jobs" not in table_names
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            upgraded = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "encrypted_contents" in upgraded
        assert "outbox_jobs" in upgraded
    finally:
        _drop_database(admin_url, database_name)


def test_hi_cross_tenant_content_foreign_key_rejects_mismatch() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    content_a = uuid.uuid4()
    message_b = uuid.uuid4()
    thread_a = uuid.uuid4()
    connection_a = uuid.uuid4()
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
                INSERT INTO encrypted_contents (
                    id, tenant_id, kind, encoding, ciphertext, content_nonce,
                    wrapped_data_key, key_wrap_nonce, algorithm, key_version,
                    aad_version, plaintext_byte_length, created_at, expires_at
                ) VALUES (
                    %s, %s, 'raw_message', 'utf8', '\\x0102', '\\x000000000000000000000000',
                    '\\x0304', '\\x000000000000000000000000', 'aes_256_gcm', 'test-kek-v1',
                    1, 2,
                    TIMESTAMPTZ '2026-07-12T09:00:00Z',
                    TIMESTAMPTZ '2026-08-12T09:00:00Z'
                )
                """,
                (content_a, tenant_a),
            )
            connection.execute(
                """
                INSERT INTO channel_connections (
                    id, tenant_id, provider, external_connection_id, status,
                    adapter_metadata, created_at, updated_at
                ) VALUES (
                    %s, %s, 'whatsapp', 'wa-hi-fk-test', 'active', '{}'::jsonb,
                    TIMESTAMPTZ '2026-07-12T09:00:00Z',
                    TIMESTAMPTZ '2026-07-12T09:00:00Z'
                )
                """,
                (connection_a, tenant_a),
            )
            connection.execute(
                """
                INSERT INTO conversation_threads (
                    id, tenant_id, channel_connection_id, external_conversation_id,
                    sales_case_id, lifecycle_status, adapter_metadata,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'thread-hi-fk-test', NULL, 'awaiting_customer', '{}'::jsonb,
                    TIMESTAMPTZ '2026-07-12T09:00:00Z',
                    TIMESTAMPTZ '2026-07-12T09:00:00Z'
                )
                """,
                (thread_a, tenant_a, connection_a),
            )
            connection.commit()
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    """
                    INSERT INTO messages (
                        id, tenant_id, conversation_thread_id, external_message_id,
                        sender_type, direction, sent_at, received_at, content_id,
                        reply_to_message_id, adapter_metadata
                    ) VALUES (
                        %s, %s, %s, 'msg-hi-fk-test', 'customer', 'inbound',
                        TIMESTAMPTZ '2026-07-12T09:00:00Z',
                        TIMESTAMPTZ '2026-07-12T09:00:00Z',
                        %s, NULL, '{}'::jsonb
                    )
                    """,
                    (message_b, tenant_b, thread_a, content_a),
                )
    finally:
        _drop_database(admin_url, database_name)
