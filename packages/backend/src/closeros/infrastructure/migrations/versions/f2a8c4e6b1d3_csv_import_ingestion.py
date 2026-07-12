"""CSV import ingestion schema and JK audit/outbox extensions.

Revision ID: f2a8c4e6b1d3
Revises: e7a1c3d5f9b2
Create Date: 2026-07-12 16:30:00.000000

Creates ``csv_import_batches`` and ``csv_import_row_errors`` with tenant-safe
composite foreign keys. Extends encrypted-content kind, outbox job kind/error
codes, and audit CHECK constraints for ingestion actions.

Rollback / remediation
----------------------
The downgrade drops CSV import tables and restores prior CHECK constraints.
Safe only on an empty schema or in an isolated test database. On populated
production data, use expand/migrate/contract.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a8c4e6b1d3"
down_revision: str | Sequence[str] | None = "e7a1c3d5f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GCM_NONCE_SIZE_BYTES = 12
_MAX_KEY_VERSION_LENGTH = 64
_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
_CSV_IMPORT_MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
_CONTENT_AAD_VERSION = 1

_PREVIOUS_CONTENT_KIND_VALUES = ("raw_message", "sanitized_message", "provider_payload")
_CONTENT_KIND_VALUES = _PREVIOUS_CONTENT_KIND_VALUES + ("csv_import",)

_PREVIOUS_OUTBOX_JOB_KIND_VALUES = (
    "webhook.normalize",
    "content.redact",
    "message.analyze",
    "notification.deliver",
    "retention.delete",
    "knowledge.index",
    "reconciliation.run",
)
_OUTBOX_JOB_KIND_VALUES = _PREVIOUS_OUTBOX_JOB_KIND_VALUES + ("csv.import",)

_PREVIOUS_OUTBOX_ERROR_CODE_VALUES = (
    "publish_failed",
    "queue_unavailable",
    "handler_failed",
    "handler_not_implemented",
    "handler_timeout",
    "resource_unavailable",
    "stale_claim",
    "transition_invalid",
    "claim_expired",
    "max_attempts_exceeded",
)
_OUTBOX_ERROR_CODE_VALUES = _PREVIOUS_OUTBOX_ERROR_CODE_VALUES + (
    "malformed_provider_event",
    "unsupported_operation",
    "missing_canonical_parent",
    "adapter_unavailable",
)

_HI_ACTION_VALUES = (
    "user.registration.completed",
    "user.email_verification.requested",
    "user.email_verification.completed",
    "auth.login.succeeded",
    "auth.login.failed",
    "auth.mfa.completed",
    "auth.mfa.failed",
    "auth.session.revoked",
    "auth.session.revoked_all",
    "auth.password_reset.requested",
    "auth.password_reset.completed",
    "auth.password.changed",
    "tenant.access.granted",
    "tenant.access.denied",
    "audit.log_viewed",
    "tenant.status.changed",
    "membership.created",
    "membership.status.changed",
    "membership.roles.changed",
    "invitation.created",
    "invitation.revoked",
    "channel_connection.created",
    "channel_connection.status.changed",
    "manager_assignment.changed",
    "encrypted_content.stored",
    "encrypted_content.accessed",
    "encrypted_content.key_rewrapped",
    "outbox.job.dead_lettered",
    "outbox.reconciliation.completed",
)

_HI_TARGET_TYPE_VALUES = (
    "user",
    "credential",
    "session",
    "tenant",
    "membership",
    "invitation",
    "channel_connection",
    "manager_assignment",
    "audit_log",
    "authentication",
    "encrypted_content",
    "outbox_job",
    "outbox_reconciliation",
)

_ACTION_VALUES = _HI_ACTION_VALUES + (
    "webhook.accepted",
    "webhook.duplicate_accepted",
    "webhook.normalized",
    "webhook.normalization_failed",
    "csv_import.uploaded",
    "csv_import.started",
    "csv_import.completed",
    "csv_import.cancelled",
)

_TARGET_TYPE_VALUES = _HI_TARGET_TYPE_VALUES + (
    "webhook_event",
    "csv_import_batch",
)

_CSV_IMPORT_STATUS_VALUES = (
    "uploaded",
    "ready",
    "processing",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
)
_CSV_DELIMITER_VALUES = ("comma", "semicolon", "tab")
_CSV_SOURCE_ENCODING_VALUES = ("utf8", "utf8_bom")
_CSV_IMPORT_ERROR_CODE_VALUES = (
    "invalid_row",
    "missing_required_field",
    "invalid_timestamp",
    "invalid_enum_value",
    "duplicate_external_message",
    "message_too_large",
    "thread_unavailable",
    "mapping_invalid",
)

_PREVIOUS_PROVIDER_VALUES = ("whatsapp", "instagram", "telegram_business")
_PROVIDER_VALUES = _PREVIOUS_PROVIDER_VALUES + ("synthetic",)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _upgrade_audit_constraints() -> None:
    op.drop_constraint(op.f("ck_audit_events_action"), "audit_events", type_="check")
    op.drop_constraint(op.f("ck_audit_events_target_type"), "audit_events", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_events_action"),
        "audit_events",
        f"action IN ({_quoted(_ACTION_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_audit_events_target_type"),
        "audit_events",
        f"target_type IN ({_quoted(_TARGET_TYPE_VALUES)})",
    )


def _downgrade_audit_constraints() -> None:
    op.drop_constraint(op.f("ck_audit_events_action"), "audit_events", type_="check")
    op.drop_constraint(op.f("ck_audit_events_target_type"), "audit_events", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_events_action"),
        "audit_events",
        f"action IN ({_quoted(_HI_ACTION_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_audit_events_target_type"),
        "audit_events",
        f"target_type IN ({_quoted(_HI_TARGET_TYPE_VALUES)})",
    )


def _upgrade_encrypted_content_constraints() -> None:
    op.drop_constraint(op.f("ck_encrypted_contents_kind"), "encrypted_contents", type_="check")
    op.drop_constraint(
        op.f("ck_encrypted_contents_plaintext_byte_length_kind_limit"),
        "encrypted_contents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_encrypted_contents_kind"),
        "encrypted_contents",
        f"kind IN ({_quoted(_CONTENT_KIND_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_encrypted_contents_plaintext_byte_length_kind_limit"),
        "encrypted_contents",
        "(kind = 'provider_payload' "
        f"AND plaintext_byte_length <= {_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'csv_import' "
        f"AND plaintext_byte_length <= {_CSV_IMPORT_MAX_PLAINTEXT_BYTES}) OR "
        "(kind NOT IN ('provider_payload', 'csv_import') "
        f"AND plaintext_byte_length <= {_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
    )


def _downgrade_encrypted_content_constraints() -> None:
    op.drop_constraint(op.f("ck_encrypted_contents_kind"), "encrypted_contents", type_="check")
    op.drop_constraint(
        op.f("ck_encrypted_contents_plaintext_byte_length_kind_limit"),
        "encrypted_contents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_encrypted_contents_kind"),
        "encrypted_contents",
        f"kind IN ({_quoted(_PREVIOUS_CONTENT_KIND_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_encrypted_contents_plaintext_byte_length_kind_limit"),
        "encrypted_contents",
        "(kind = 'provider_payload' "
        f"AND plaintext_byte_length <= {_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES}) OR "
        "(kind <> 'provider_payload' "
        f"AND plaintext_byte_length <= {_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
    )


def _upgrade_outbox_constraints() -> None:
    op.drop_constraint(op.f("ck_outbox_jobs_job_kind"), "outbox_jobs", type_="check")
    op.drop_constraint(op.f("ck_outbox_jobs_last_error_code"), "outbox_jobs", type_="check")
    op.drop_constraint(
        op.f("ck_outbox_job_attempts_error_code"),
        "outbox_job_attempts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_outbox_jobs_job_kind"),
        "outbox_jobs",
        f"job_kind IN ({_quoted(_OUTBOX_JOB_KIND_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_outbox_jobs_last_error_code"),
        "outbox_jobs",
        f"last_error_code IS NULL OR last_error_code IN ({_quoted(_OUTBOX_ERROR_CODE_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_outbox_job_attempts_error_code"),
        "outbox_job_attempts",
        f"error_code IS NULL OR error_code IN ({_quoted(_OUTBOX_ERROR_CODE_VALUES)})",
    )


def _downgrade_outbox_constraints() -> None:
    op.drop_constraint(op.f("ck_outbox_jobs_job_kind"), "outbox_jobs", type_="check")
    op.drop_constraint(op.f("ck_outbox_jobs_last_error_code"), "outbox_jobs", type_="check")
    op.drop_constraint(
        op.f("ck_outbox_job_attempts_error_code"),
        "outbox_job_attempts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_outbox_jobs_job_kind"),
        "outbox_jobs",
        f"job_kind IN ({_quoted(_PREVIOUS_OUTBOX_JOB_KIND_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_outbox_jobs_last_error_code"),
        "outbox_jobs",
        "last_error_code IS NULL OR last_error_code IN ("
        f"{_quoted(_PREVIOUS_OUTBOX_ERROR_CODE_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_outbox_job_attempts_error_code"),
        "outbox_job_attempts",
        f"error_code IS NULL OR error_code IN ({_quoted(_PREVIOUS_OUTBOX_ERROR_CODE_VALUES)})",
    )


def _upgrade_provider_constraints() -> None:
    op.drop_constraint(
        op.f("ck_channel_connections_provider"), "channel_connections", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_channel_connections_provider"),
        "channel_connections",
        f"provider IN ({_quoted(_PROVIDER_VALUES)})",
    )


def _downgrade_provider_constraints() -> None:
    op.drop_constraint(
        op.f("ck_channel_connections_provider"), "channel_connections", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_channel_connections_provider"),
        "channel_connections",
        f"provider IN ({_quoted(_PREVIOUS_PROVIDER_VALUES)})",
    )


def upgrade() -> None:
    _upgrade_audit_constraints()
    _upgrade_encrypted_content_constraints()
    _upgrade_outbox_constraints()
    _upgrade_provider_constraints()

    op.create_table(
        "csv_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creator_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delimiter", sa.String(length=16), nullable=False),
        sa.Column("source_encoding", sa.String(length=16), nullable=False),
        sa.Column(
            "lawful_source_confirmed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("next_row_number", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CSV_IMPORT_STATUS_VALUES)})",
            name=op.f("ck_csv_import_batches_status"),
        ),
        sa.CheckConstraint(
            f"delimiter IN ({_quoted(_CSV_DELIMITER_VALUES)})",
            name=op.f("ck_csv_import_batches_delimiter"),
        ),
        sa.CheckConstraint(
            f"source_encoding IN ({_quoted(_CSV_SOURCE_ENCODING_VALUES)})",
            name=op.f("ck_csv_import_batches_source_encoding"),
        ),
        sa.CheckConstraint(
            "total_rows >= 0", name=op.f("ck_csv_import_batches_total_rows_non_negative")
        ),
        sa.CheckConstraint(
            "next_row_number >= 1",
            name=op.f("ck_csv_import_batches_next_row_number_positive"),
        ),
        sa.CheckConstraint(
            "succeeded_count >= 0",
            name=op.f("ck_csv_import_batches_succeeded_count_non_negative"),
        ),
        sa.CheckConstraint(
            "failed_count >= 0",
            name=op.f("ck_csv_import_batches_failed_count_non_negative"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_csv_import_batches_version_positive")),
        sa.CheckConstraint(
            "expires_at >= created_at",
            name=op.f("ck_csv_import_batches_expires_at_not_before_created_at"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f("fk_csv_import_batches_tenant_id_channel_connection_id_channel_connections"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_csv_import_batches_tenant_id_source_content_id_encrypted_contents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_csv_import_batches")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_csv_import_batches_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_csv_import_batches_tenant_id_status_created_at"),
        "csv_import_batches",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("uq_csv_import_batches_tenant_id_idempotency_key"),
        "csv_import_batches",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "csv_import_row_errors",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "row_number >= 1", name=op.f("ck_csv_import_row_errors_row_number_positive")
        ),
        sa.CheckConstraint(
            f"error_code IN ({_quoted(_CSV_IMPORT_ERROR_CODE_VALUES)})",
            name=op.f("ck_csv_import_row_errors_error_code"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            ["csv_import_batches.tenant_id", "csv_import_batches.id"],
            name=op.f("fk_csv_import_row_errors_tenant_id_import_id_csv_import_batches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "import_id",
            "row_number",
            name=op.f("pk_csv_import_row_errors"),
        ),
    )
    op.create_index(
        op.f("ix_csv_import_row_errors_tenant_id_import_id"),
        "csv_import_row_errors",
        ["tenant_id", "import_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_csv_import_row_errors_tenant_id_import_id"),
        table_name="csv_import_row_errors",
    )
    op.drop_table("csv_import_row_errors")

    op.drop_index(
        op.f("uq_csv_import_batches_tenant_id_idempotency_key"),
        table_name="csv_import_batches",
    )
    op.drop_index(
        op.f("ix_csv_import_batches_tenant_id_status_created_at"),
        table_name="csv_import_batches",
    )
    op.drop_table("csv_import_batches")

    _downgrade_outbox_constraints()
    _downgrade_encrypted_content_constraints()
    _downgrade_audit_constraints()
    _downgrade_provider_constraints()
