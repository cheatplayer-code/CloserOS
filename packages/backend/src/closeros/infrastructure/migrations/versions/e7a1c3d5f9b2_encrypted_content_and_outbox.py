"""Encrypted content storage and transactional outbox schema.

Revision ID: e7a1c3d5f9b2
Revises: d4e8f1a2b3c5
Create Date: 2026-07-12 15:30:00.000000

Creates ``encrypted_contents``, ``outbox_jobs``, and ``outbox_job_attempts`` with
tenant-safe composite foreign keys from canonical message and webhook tables.
Extends ``audit_events`` CHECK constraints for encrypted-content and outbox audit
actions and target types.

Rollback / remediation
----------------------
The downgrade drops outbox tables, removes content foreign keys and the webhook
payload column, drops ``encrypted_contents``, and restores the prior audit CHECK
constraints. Safe only on an empty schema or in an isolated test database. On
populated production data, use expand/migrate/contract.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7a1c3d5f9b2"
down_revision: str | Sequence[str] | None = "d4e8f1a2b3c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GCM_NONCE_SIZE_BYTES = 12
_MAX_KEY_VERSION_LENGTH = 64
_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
_CONTENT_AAD_VERSION = 1

_CONTENT_KIND_VALUES = ("raw_message", "sanitized_message", "provider_payload")
_CONTENT_ENCODING_VALUES = ("utf8", "json", "binary")
_ENCRYPTION_ALGORITHM_VALUES = ("aes_256_gcm",)

_OUTBOX_JOB_KIND_VALUES = (
    "webhook.normalize",
    "content.redact",
    "message.analyze",
    "notification.deliver",
    "retention.delete",
    "knowledge.index",
    "reconciliation.run",
)
_OUTBOX_JOB_STATE_VALUES = (
    "pending",
    "publishing",
    "published",
    "processing",
    "retry_scheduled",
    "succeeded",
    "dead_letter",
    "cancelled",
)
_OUTBOX_JOB_PHASE_VALUES = ("publisher", "processor")
_OUTBOX_ATTEMPT_OUTCOME_VALUES = ("succeeded", "failed", "reclaimed")
_OUTBOX_ERROR_CODE_VALUES = (
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

_PREVIOUS_ACTION_VALUES = (
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
)

_PREVIOUS_TARGET_TYPE_VALUES = (
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
)

_ACTION_VALUES = _PREVIOUS_ACTION_VALUES + (
    "encrypted_content.stored",
    "encrypted_content.accessed",
    "encrypted_content.key_rewrapped",
    "outbox.job.dead_lettered",
    "outbox.reconciliation.completed",
)

_TARGET_TYPE_VALUES = _PREVIOUS_TARGET_TYPE_VALUES + (
    "encrypted_content",
    "outbox_job",
    "outbox_reconciliation",
)


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
        f"action IN ({_quoted(_PREVIOUS_ACTION_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_audit_events_target_type"),
        "audit_events",
        f"target_type IN ({_quoted(_PREVIOUS_TARGET_TYPE_VALUES)})",
    )


def upgrade() -> None:
    _upgrade_audit_constraints()

    op.create_table(
        "encrypted_contents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("encoding", sa.String(length=16), nullable=False),
        sa.Column("ciphertext", postgresql.BYTEA(), nullable=False),
        sa.Column("content_nonce", postgresql.BYTEA(), nullable=False),
        sa.Column("wrapped_data_key", postgresql.BYTEA(), nullable=False),
        sa.Column("key_wrap_nonce", postgresql.BYTEA(), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False),
        sa.Column("key_version", sa.String(length=_MAX_KEY_VERSION_LENGTH), nullable=False),
        sa.Column("aad_version", sa.Integer(), nullable=False),
        sa.Column("plaintext_byte_length", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"kind IN ({_quoted(_CONTENT_KIND_VALUES)})",
            name=op.f("ck_encrypted_contents_kind"),
        ),
        sa.CheckConstraint(
            f"encoding IN ({_quoted(_CONTENT_ENCODING_VALUES)})",
            name=op.f("ck_encrypted_contents_encoding"),
        ),
        sa.CheckConstraint(
            f"algorithm IN ({_quoted(_ENCRYPTION_ALGORITHM_VALUES)})",
            name=op.f("ck_encrypted_contents_algorithm"),
        ),
        sa.CheckConstraint(
            "octet_length(ciphertext) >= 1",
            name=op.f("ck_encrypted_contents_ciphertext_not_empty"),
        ),
        sa.CheckConstraint(
            f"octet_length(content_nonce) = {_GCM_NONCE_SIZE_BYTES}",
            name=op.f("ck_encrypted_contents_content_nonce_length"),
        ),
        sa.CheckConstraint(
            "octet_length(wrapped_data_key) >= 1",
            name=op.f("ck_encrypted_contents_wrapped_data_key_not_empty"),
        ),
        sa.CheckConstraint(
            f"octet_length(key_wrap_nonce) = {_GCM_NONCE_SIZE_BYTES}",
            name=op.f("ck_encrypted_contents_key_wrap_nonce_length"),
        ),
        sa.CheckConstraint(
            "plaintext_byte_length >= 1",
            name=op.f("ck_encrypted_contents_plaintext_byte_length_positive"),
        ),
        sa.CheckConstraint(
            "(kind = 'provider_payload' "
            f"AND plaintext_byte_length <= {_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES}) OR "
            "(kind <> 'provider_payload' "
            f"AND plaintext_byte_length <= {_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
            name=op.f("ck_encrypted_contents_plaintext_byte_length_kind_limit"),
        ),
        sa.CheckConstraint(
            f"aad_version >= {_CONTENT_AAD_VERSION}",
            name=op.f("ck_encrypted_contents_aad_version"),
        ),
        sa.CheckConstraint(
            f"key_version ~ '^[A-Za-z0-9][A-Za-z0-9_-]{{0,{_MAX_KEY_VERSION_LENGTH - 1}}}$'",
            name=op.f("ck_encrypted_contents_key_version_format"),
        ),
        sa.CheckConstraint(
            "expires_at >= created_at",
            name=op.f("ck_encrypted_contents_expires_at_not_before_created_at"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_encrypted_contents")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_encrypted_contents_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_encrypted_contents_tenant_id_kind_created_at"),
        "encrypted_contents",
        ["tenant_id", "kind", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_encrypted_contents_tenant_id_expires_at"),
        "encrypted_contents",
        ["tenant_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_encrypted_contents_tenant_id_key_version"),
        "encrypted_contents",
        ["tenant_id", "key_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_encrypted_contents_expires_at_tenant_id"),
        "encrypted_contents",
        ["expires_at", "tenant_id"],
        unique=False,
    )

    op.add_column(
        "webhook_events",
        sa.Column("encrypted_payload_content_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_foreign_key(
        op.f("fk_messages_tenant_id_content_id_encrypted_contents"),
        "messages",
        "encrypted_contents",
        ["tenant_id", "content_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_message_edit_events_tenant_id_content_id_encrypted_contents"),
        "message_edit_events",
        "encrypted_contents",
        ["tenant_id", "content_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_webhook_events_tenant_id_encrypted_payload_content_id_encrypted_contents"),
        "webhook_events",
        "encrypted_contents",
        ["tenant_id", "encrypted_payload_content_id"],
        ["tenant_id", "id"],
    )

    op.create_table(
        "outbox_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_kind", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secondary_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("deduplication_key", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("available_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("claim_expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processing_started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"job_kind IN ({_quoted(_OUTBOX_JOB_KIND_VALUES)})",
            name=op.f("ck_outbox_jobs_job_kind"),
        ),
        sa.CheckConstraint(
            f"state IN ({_quoted(_OUTBOX_JOB_STATE_VALUES)})",
            name=op.f("ck_outbox_jobs_state"),
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name=op.f("ck_outbox_jobs_priority_bounds"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_outbox_jobs_attempt_count_non_negative"),
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name=op.f("ck_outbox_jobs_max_attempts_positive"),
        ),
        sa.CheckConstraint(
            "schema_version >= 1 AND schema_version <= 1000",
            name=op.f("ck_outbox_jobs_schema_version_bounds"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_outbox_jobs_version_positive"),
        ),
        sa.CheckConstraint(
            "deduplication_key ~ '^[a-z][a-z0-9_-]{0,127}$'",
            name=op.f("ck_outbox_jobs_deduplication_key_format"),
        ),
        sa.CheckConstraint(
            "resource_type ~ '^[a-z][a-z0-9_]{0,63}$'",
            name=op.f("ck_outbox_jobs_resource_type_format"),
        ),
        sa.CheckConstraint(
            "claimed_by IS NULL OR claimed_by ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name=op.f("ck_outbox_jobs_claimed_by_format"),
        ),
        sa.CheckConstraint(
            f"last_error_code IS NULL OR last_error_code IN ({_quoted(_OUTBOX_ERROR_CODE_VALUES)})",
            name=op.f("ck_outbox_jobs_last_error_code"),
        ),
        sa.CheckConstraint(
            "(job_kind = 'reconciliation.run' AND tenant_id IS NULL) OR "
            "(job_kind <> 'reconciliation.run' AND tenant_id IS NOT NULL)",
            name=op.f("ck_outbox_jobs_tenant_scope"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_jobs")),
    )
    op.create_index(
        op.f("ix_outbox_jobs_state_available_at_priority"),
        "outbox_jobs",
        ["state", "available_at", "priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_jobs_claim_expires_at_state"),
        "outbox_jobs",
        ["claim_expires_at", "state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_jobs_tenant_id_created_at"),
        "outbox_jobs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_jobs_state_created_at"),
        "outbox_jobs",
        ["state", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("uq_outbox_jobs_tenant_id_deduplication_key"),
        "outbox_jobs",
        ["tenant_id", "deduplication_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        op.f("uq_outbox_jobs_global_deduplication_key"),
        "outbox_jobs",
        ["deduplication_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    op.create_table(
        "outbox_job_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            f"phase IN ({_quoted(_OUTBOX_JOB_PHASE_VALUES)})",
            name=op.f("ck_outbox_job_attempts_phase"),
        ),
        sa.CheckConstraint(
            f"outcome IN ({_quoted(_OUTBOX_ATTEMPT_OUTCOME_VALUES)})",
            name=op.f("ck_outbox_job_attempts_outcome"),
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name=op.f("ck_outbox_job_attempts_attempt_number_positive"),
        ),
        sa.CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_quoted(_OUTBOX_ERROR_CODE_VALUES)})",
            name=op.f("ck_outbox_job_attempts_error_code"),
        ),
        sa.CheckConstraint(
            "finished_at >= started_at",
            name=op.f("ck_outbox_job_attempts_finished_at_ordering"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["outbox_jobs.id"],
            name=op.f("fk_outbox_job_attempts_job_id_outbox_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_job_attempts")),
    )
    op.create_index(
        op.f("ix_outbox_job_attempts_job_id_attempt_number"),
        "outbox_job_attempts",
        ["job_id", "attempt_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_outbox_job_attempts_job_id_attempt_number"),
        table_name="outbox_job_attempts",
    )
    op.drop_table("outbox_job_attempts")

    op.drop_index(op.f("uq_outbox_jobs_global_deduplication_key"), table_name="outbox_jobs")
    op.drop_index(op.f("uq_outbox_jobs_tenant_id_deduplication_key"), table_name="outbox_jobs")
    op.drop_index(op.f("ix_outbox_jobs_state_created_at"), table_name="outbox_jobs")
    op.drop_index(op.f("ix_outbox_jobs_tenant_id_created_at"), table_name="outbox_jobs")
    op.drop_index(op.f("ix_outbox_jobs_claim_expires_at_state"), table_name="outbox_jobs")
    op.drop_index(
        op.f("ix_outbox_jobs_state_available_at_priority"),
        table_name="outbox_jobs",
    )
    op.drop_table("outbox_jobs")

    op.drop_constraint(
        op.f("fk_webhook_events_tenant_id_encrypted_payload_content_id_encrypted_contents"),
        "webhook_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_message_edit_events_tenant_id_content_id_encrypted_contents"),
        "message_edit_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_messages_tenant_id_content_id_encrypted_contents"),
        "messages",
        type_="foreignkey",
    )
    op.drop_column("webhook_events", "encrypted_payload_content_id")

    op.drop_index(
        op.f("ix_encrypted_contents_expires_at_tenant_id"),
        table_name="encrypted_contents",
    )
    op.drop_index(
        op.f("ix_encrypted_contents_tenant_id_key_version"),
        table_name="encrypted_contents",
    )
    op.drop_index(
        op.f("ix_encrypted_contents_tenant_id_expires_at"),
        table_name="encrypted_contents",
    )
    op.drop_index(
        op.f("ix_encrypted_contents_tenant_id_kind_created_at"),
        table_name="encrypted_contents",
    )
    op.drop_table("encrypted_contents")

    _downgrade_audit_constraints()
