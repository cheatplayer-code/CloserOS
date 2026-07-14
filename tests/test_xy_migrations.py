"""PostgreSQL migration tests for XY production operations schema."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import create_migration_engine
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _rebuild_database_url,
    _sqlalchemy_database_url,
)

XY_REVISION = "c4e8a2b6d1f0"
PRE_XY_REVISION = "b3d7f1a4c8e6"
_NOW = "TIMESTAMPTZ '2026-07-12T12:00:00Z'"


def _synthetic_script_url() -> str:
    return "postgresql+psycopg://{user}:{password}@{host}:{port}/{database}".format(
        user="local",
        password="local",
        host="127.0.0.1",
        port=5432,
        database="local",
    )


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_xy_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


@contextmanager
def _isolated_xy_database(*, revision: str = "head") -> Iterator[tuple[str, str, str, Engine]]:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    command.upgrade(config, revision)
    engine = create_migration_engine(database_url)
    try:
        yield admin_url, database_name, database_url, engine
    finally:
        engine.dispose()
        _drop_database(admin_url, database_name)


def _column_map(engine: Engine, table_name: str) -> dict[str, dict[str, object]]:
    inspector = inspect(engine)
    return {str(column["name"]): dict(column) for column in inspector.get_columns(table_name)}


def _foreign_key_ondelete(
    engine: Engine,
    *,
    table_name: str,
    constrained_columns: list[str],
) -> str | None:
    inspector = inspect(engine)
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key["constrained_columns"] == constrained_columns:
            options = foreign_key.get("options") or {}
            ondelete = options.get("ondelete")
            return str(ondelete) if ondelete is not None else None
    raise AssertionError(
        f"foreign key on {table_name}({', '.join(constrained_columns)}) was not found"
    )


def _seed_tenant(connection: psycopg.Connection, *, tenant_id: uuid.UUID) -> None:
    connection.execute(
        """
        INSERT INTO tenants (
            id, name, status, time_zone,
            raw_message_days, sanitized_message_days, ai_output_days,
            audit_log_days, backup_days, post_contract_deletion_days
        ) VALUES (%s, %s, %s, %s, 30, 30, 30, 365, 30, 90)
        """,
        (tenant_id, f"Tenant {tenant_id.hex[:8]}", "active", "UTC"),
    )


def _seed_user(connection: psycopg.Connection, *, user_id: uuid.UUID) -> None:
    connection.execute(
        "INSERT INTO users (id, status) VALUES (%s, %s)",
        (user_id, "active"),
    )


def _insert_encrypted_content(
    connection: psycopg.Connection,
    *,
    content_id: uuid.UUID,
    tenant_id: uuid.UUID,
    kind: str = "notification_payload",
    plaintext_byte_length: int = 16,
) -> None:
    connection.execute(
        f"""
        INSERT INTO encrypted_contents (
            id, tenant_id, kind, encoding, ciphertext, content_nonce,
            wrapped_data_key, key_wrap_nonce, algorithm, key_version,
            aad_version, plaintext_byte_length, created_at, expires_at
        ) VALUES (
            %s, %s, %s, 'utf8', '\\x0102', '\\x000000000000000000000000',
            '\\x0304', '\\x000000000000000000000000', 'aes_256_gcm', 'test-kek-v1',
            1, %s,
            {_NOW},
            TIMESTAMPTZ '2026-08-12T12:00:00Z'
        )
        """,
        (content_id, tenant_id, kind, plaintext_byte_length),
    )


def test_xy_migration_revision_is_head() -> None:
    config = build_alembic_config(_synthetic_script_url())
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "c3e5a7b9d1f0"


def test_xy_migration_upgrade_creates_tables() -> None:
    with _isolated_xy_database() as (_, _, _, engine):
        table_names = set(inspect(engine).get_table_names())
        assert {
            "notification_deliveries",
            "notification_delivery_attempts",
            "legal_holds",
            "retention_purge_runs",
            "retention_purge_batches",
            "crm_connections",
            "crm_field_mappings",
            "crm_sync_checkpoints",
            "crm_sync_attempts",
            "crm_conflicts",
            "user_mfa_totp_enrollments",
        }.issubset(table_names)


def test_xy_migration_retention_run_schema_contract() -> None:
    with _isolated_xy_database() as (_, _, _, engine):
        columns = _column_map(engine, "retention_purge_runs")
        assert "claim_token" in columns
        assert columns["claim_token"]["nullable"] is True
        assert "claim_expires_at" in columns
        assert columns["claim_expires_at"]["nullable"] is True
        assert "version" in columns
        assert columns["version"]["nullable"] is False

        inspector = inspect(engine)
        checks = {
            item["name"]: item for item in inspector.get_check_constraints("retention_purge_runs")
        }
        version_checks = [check for check in checks.values() if "version >= 1" in check["sqltext"]]
        assert version_checks

        uniques = inspector.get_unique_constraints("retention_purge_runs")
        assert any(
            unique["name"] == "uq_retention_purge_runs_tenant_id_id"
            and unique["column_names"] == ["tenant_id", "id"]
            for unique in uniques
        )

        indexes = inspector.get_indexes("retention_purge_runs")
        assert any(
            index["name"] == "ix_retention_purge_runs_tenant_created"
            and index["column_names"] == ["tenant_id", "created_at"]
            for index in indexes
        )


def test_xy_migration_notification_and_retention_foreign_keys() -> None:
    with _isolated_xy_database() as (_, _, _, engine):
        notification_payload_ondelete = _foreign_key_ondelete(
            engine,
            table_name="notification_deliveries",
            constrained_columns=["payload_tenant_id", "encrypted_payload_content_id"],
        )
        assert notification_payload_ondelete == "SET NULL"

        provider_media_ondelete = _foreign_key_ondelete(
            engine,
            table_name="provider_media_references",
            constrained_columns=["tenant_id", "encrypted_content_id"],
        )
        assert provider_media_ondelete in {None, "NO ACTION", "RESTRICT"}

        retention_batch_fks = inspect(engine).get_foreign_keys("retention_purge_batches")
        assert any(
            foreign_key["referred_table"] == "retention_purge_runs"
            and foreign_key["constrained_columns"] == ["tenant_id", "purge_run_id"]
            for foreign_key in retention_batch_fks
        )

        batch_columns = _column_map(engine, "retention_purge_batches")
        assert batch_columns["deleted_content_id"]["nullable"] is False
        assert not any(
            foreign_key["constrained_columns"] == ["deleted_content_id"]
            for foreign_key in retention_batch_fks
        )


def test_xy_migration_valid_rows_and_constraint_violations() -> None:
    with _isolated_xy_database() as (_, database_name, database_url, _):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        content_id = uuid.uuid4()
        delivery_id = uuid.uuid4()
        attempt_id = uuid.uuid4()
        legal_hold_id = uuid.uuid4()
        purge_run_id = uuid.uuid4()
        purge_batch_id = uuid.uuid4()
        claim_token = uuid.uuid4()

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            _seed_tenant(connection, tenant_id=tenant_id)
            _seed_user(connection, user_id=user_id)
            _insert_encrypted_content(
                connection,
                content_id=content_id,
                tenant_id=tenant_id,
            )
            connection.execute(
                f"""
                INSERT INTO notification_deliveries (
                    id, tenant_id, payload_tenant_id, kind, status,
                    template_code, template_version, recipient_hash,
                    encrypted_payload_content_id, idempotency_key, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'email_verification', 'pending',
                    'verify-email', 1, 'recipient-hash',
                    %s, %s, 0,
                    {_NOW}, {_NOW}
                )
                """,
                (delivery_id, tenant_id, tenant_id, content_id, f"idem-{delivery_id.hex[:8]}"),
            )
            connection.execute(
                f"""
                INSERT INTO notification_delivery_attempts (
                    id, tenant_id, delivery_id, attempt_number, outcome,
                    started_at, finished_at
                ) VALUES (
                    %s, %s, %s, 1, 'failed',
                    {_NOW}, {_NOW}
                )
                """,
                (attempt_id, tenant_id, delivery_id),
            )
            connection.execute(
                f"""
                INSERT INTO legal_holds (
                    id, tenant_id, status, reason_code, created_by_user_id,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, 'active', 'litigation-hold', %s,
                    {_NOW}, {_NOW}
                )
                """,
                (legal_hold_id, tenant_id, user_id),
            )
            connection.execute(
                f"""
                INSERT INTO retention_purge_runs (
                    id, tenant_id, status, dry_run, expires_before,
                    items_scanned, items_deleted, items_skipped_legal_hold,
                    claim_token, claim_expires_at, version,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, 'pending', false, {_NOW},
                    0, 0, 0,
                    %s, TIMESTAMPTZ '2026-07-12T12:05:00Z', 1,
                    {_NOW}, {_NOW}
                )
                """,
                (purge_run_id, tenant_id, claim_token),
            )
            connection.execute(
                f"""
                INSERT INTO retention_purge_batches (
                    id, tenant_id, purge_run_id, deleted_content_id, status,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, 'completed',
                    {_NOW}
                )
                """,
                (purge_batch_id, tenant_id, purge_run_id, content_id),
            )
            connection.commit()

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    f"""
                    INSERT INTO notification_deliveries (
                        id, tenant_id, payload_tenant_id, kind, status,
                        template_code, template_version, recipient_hash,
                        idempotency_key, attempt_count, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, 'invalid_kind', 'pending',
                        'verify-email', 1, 'recipient-hash',
                        %s, 0, {_NOW}, {_NOW}
                    )
                    """,
                    (
                        uuid.uuid4(),
                        tenant_id,
                        tenant_id,
                        f"idem-invalid-kind-{uuid.uuid4().hex[:8]}",
                    ),
                )
            connection.rollback()

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    f"""
                    INSERT INTO retention_purge_runs (
                        id, tenant_id, status, dry_run, expires_before,
                        items_scanned, items_deleted, items_skipped_legal_hold,
                        version, created_at, updated_at
                    ) VALUES (
                        %s, %s, 'pending', false, {_NOW},
                        0, 0, 0,
                        0, {_NOW}, {_NOW}
                    )
                    """,
                    (uuid.uuid4(), tenant_id),
                )
            connection.rollback()

            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    f"""
                    INSERT INTO retention_purge_batches (
                        id, tenant_id, purge_run_id, deleted_content_id, status,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, 'completed',
                        {_NOW}
                    )
                    """,
                    (uuid.uuid4(), tenant_id, uuid.uuid4(), content_id),
                )
            connection.rollback()


def test_notification_payload_parent_delete_sets_composite_reference_to_null() -> None:
    with _isolated_xy_database() as (_, database_name, database_url, _):
        tenant_id = uuid.uuid4()
        content_id = uuid.uuid4()
        delivery_id = uuid.uuid4()

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            _seed_tenant(connection, tenant_id=tenant_id)
            _insert_encrypted_content(
                connection,
                content_id=content_id,
                tenant_id=tenant_id,
            )
            connection.execute(
                f"""
                INSERT INTO notification_deliveries (
                    id, tenant_id, payload_tenant_id, kind, status,
                    template_code, template_version, recipient_hash,
                    encrypted_payload_content_id, idempotency_key, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'password_reset', 'pending',
                    'reset-password', 1, 'recipient-hash',
                    %s, %s, 0,
                    {_NOW}, {_NOW}
                )
                """,
                (delivery_id, tenant_id, tenant_id, content_id, f"idem-{delivery_id.hex[:8]}"),
            )
            connection.commit()

            connection.execute(
                "DELETE FROM encrypted_contents WHERE id = %s AND tenant_id = %s",
                (content_id, tenant_id),
            )
            connection.commit()

            row = connection.execute(
                """
                SELECT tenant_id, encrypted_payload_content_id, payload_tenant_id,
                       template_code, recipient_hash
                FROM notification_deliveries
                WHERE id = %s
                """,
                (delivery_id,),
            ).fetchone()
            assert row is not None
            assert row[0] == tenant_id
            assert row[1] is None
            assert row[2] is None
            assert row[3] == "reset-password"
            assert row[4] == "recipient-hash"


def test_notification_payload_reference_rejects_half_null_state() -> None:
    with _isolated_xy_database() as (_, database_name, database_url, _):
        tenant_id = uuid.uuid4()
        content_id = uuid.uuid4()
        delivery_id = uuid.uuid4()

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            _seed_tenant(connection, tenant_id=tenant_id)
            _insert_encrypted_content(
                connection,
                content_id=content_id,
                tenant_id=tenant_id,
            )

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    f"""
                    INSERT INTO notification_deliveries (
                        id, tenant_id, payload_tenant_id, kind, status,
                        template_code, template_version, recipient_hash,
                        encrypted_payload_content_id, idempotency_key, attempt_count,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, 'password_reset', 'pending',
                        'reset-password', 1, 'recipient-hash',
                        NULL, %s, 0,
                        {_NOW}, {_NOW}
                    )
                    """,
                    (delivery_id, tenant_id, tenant_id, f"idem-{delivery_id.hex[:8]}"),
                )
            connection.rollback()

            half_delivery_id = uuid.uuid4()
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    f"""
                    INSERT INTO notification_deliveries (
                        id, tenant_id, payload_tenant_id, kind, status,
                        template_code, template_version, recipient_hash,
                        encrypted_payload_content_id, idempotency_key, attempt_count,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, NULL, 'password_reset', 'pending',
                        'reset-password', 1, 'recipient-hash',
                        %s, %s, 0,
                        {_NOW}, {_NOW}
                    )
                    """,
                    (half_delivery_id, tenant_id, content_id, f"idem-{half_delivery_id.hex[:8]}"),
                )
            connection.rollback()


def test_xy_retention_batch_history_survives_encrypted_content_delete() -> None:
    with _isolated_xy_database() as (_, database_name, database_url, _):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        content_id = uuid.uuid4()
        purge_run_id = uuid.uuid4()
        purge_batch_id = uuid.uuid4()

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            _seed_tenant(connection, tenant_id=tenant_id)
            _seed_user(connection, user_id=user_id)
            _insert_encrypted_content(
                connection,
                content_id=content_id,
                tenant_id=tenant_id,
            )
            connection.execute(
                f"""
                INSERT INTO retention_purge_runs (
                    id, tenant_id, status, dry_run, expires_before,
                    items_scanned, items_deleted, items_skipped_legal_hold,
                    version, created_at, updated_at
                ) VALUES (
                    %s, %s, 'completed', false, {_NOW},
                    1, 1, 0,
                    1, {_NOW}, {_NOW}
                )
                """,
                (purge_run_id, tenant_id),
            )
            connection.execute(
                f"""
                INSERT INTO retention_purge_batches (
                    id, tenant_id, purge_run_id, deleted_content_id, status,
                    created_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, 'completed',
                    {_NOW}, {_NOW}
                )
                """,
                (purge_batch_id, tenant_id, purge_run_id, content_id),
            )
            connection.commit()

            connection.execute(
                "DELETE FROM encrypted_contents WHERE id = %s AND tenant_id = %s",
                (content_id, tenant_id),
            )
            connection.commit()

            row = connection.execute(
                """
                SELECT deleted_content_id, status
                FROM retention_purge_batches
                WHERE id = %s
                """,
                (purge_batch_id,),
            ).fetchone()
            assert row is not None
            assert row[0] == content_id
            assert row[1] == "completed"


def test_xy_tenant_composite_foreign_key_rejects_mismatch() -> None:
    with _isolated_xy_database() as (_, database_name, database_url, _):
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        content_a = uuid.uuid4()
        delivery_id = uuid.uuid4()

        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            _seed_tenant(connection, tenant_id=tenant_a)
            _seed_tenant(connection, tenant_id=tenant_b)
            _insert_encrypted_content(
                connection,
                content_id=content_a,
                tenant_id=tenant_a,
            )
            connection.commit()

            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    f"""
                    INSERT INTO notification_deliveries (
                        id, tenant_id, payload_tenant_id, kind, status,
                        template_code, template_version, recipient_hash,
                        encrypted_payload_content_id, idempotency_key, attempt_count,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, 'system_alert', 'pending',
                        'system-alert', 1, 'recipient-hash',
                        %s, %s, 0,
                        {_NOW}, {_NOW}
                    )
                    """,
                    (
                        delivery_id,
                        tenant_b,
                        tenant_b,
                        content_a,
                        f"idem-cross-tenant-{delivery_id.hex[:8]}",
                    ),
                )


def test_xy_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, XY_REVISION)
        command.downgrade(config, PRE_XY_REVISION)

        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        assert "notification_deliveries" not in table_names
        assert "retention_purge_runs" not in table_names
        assert "crm_connections" not in table_names

        command.upgrade(config, "head")

        engine = create_migration_engine(database_url)
        try:
            upgraded = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        assert "notification_deliveries" in upgraded
        assert "retention_purge_runs" in upgraded
        assert "crm_connections" in upgraded
    finally:
        _drop_database(admin_url, database_name)
