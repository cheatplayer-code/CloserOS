"""XY production operations schema and constraint extensions.

Revision ID: c4e8a2b6d1f0
Revises: b3d7f1a4c8e6

Creates notification delivery, legal hold, retention purge, and CRM tables.
Extends outbox job kind, media quarantine status, and audit CHECK constraints.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e8a2b6d1f0"
down_revision: str | Sequence[str] | None = "b3d7f1a4c8e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREVIOUS_OUTBOX_JOB_KIND_VALUES = (
    "webhook.normalize",
    "content.redact",
    "message.analyze",
    "notification.deliver",
    "retention.delete",
    "knowledge.index",
    "reconciliation.run",
    "csv.import",
    "metrics.recalculate",
    "provider.message.send",
    "provider.templates.sync",
)
_OUTBOX_JOB_KIND_VALUES = _PREVIOUS_OUTBOX_JOB_KIND_VALUES + (
    "media.fetch",
    "media.scan",
    "crm.sync",
)

_PREVIOUS_MEDIA_QUARANTINE_VALUES = (
    "quarantined_pending_scan",
    "scan_passed",
    "scan_failed",
    "fetch_unavailable",
)
_MEDIA_QUARANTINE_VALUES = (
    "fetching",
    "fetch_failed",
    "fetch_unavailable",
    "quarantined_pending_scan",
    "scanning",
    "clean",
    "infected",
    "scan_passed",
    "scan_failed",
)

_NOTIFICATION_KIND_VALUES = (
    "email_verification",
    "password_reset",
    "outbound_approval",
    "system_alert",
)
_NOTIFICATION_STATUS_VALUES = ("pending", "delivering", "succeeded", "failed", "cancelled")
_NOTIFICATION_ATTEMPT_OUTCOME_VALUES = ("succeeded", "failed", "transient_failed")
_LEGAL_HOLD_STATUS_VALUES = ("active", "released")
_RETENTION_RUN_STATUS_VALUES = ("pending", "running", "completed", "failed", "cancelled", "paused")
_RETENTION_BATCH_STATUS_VALUES = ("pending", "completed", "failed", "skipped_legal_hold")
_CRM_PROVIDER_VALUES = ("bitrix24",)
_CRM_CONNECTION_STATUS_VALUES = (
    "draft",
    "active",
    "degraded",
    "reauthorization_required",
    "revoked",
    "disabled",
)
_CRM_MAPPING_STATUS_VALUES = ("draft", "active", "disabled")
_CRM_SYNC_DIRECTION_VALUES = ("inbound", "outbound")
_CRM_ATTEMPT_STATUS_VALUES = ("started", "succeeded", "failed")
_CRM_CONFLICT_STATUS_VALUES = ("open", "resolved", "ignored")
_CRM_CONFLICT_RESOLUTION_VALUES = ("use_crm", "use_closeros", "ignore")

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
    "encrypted_content.stored",
    "encrypted_content.accessed",
    "encrypted_content.key_rewrapped",
    "outbox.job.dead_lettered",
    "outbox.reconciliation.completed",
    "webhook.accepted",
    "webhook.duplicate_accepted",
    "webhook.normalized",
    "webhook.normalization_failed",
    "csv_import.uploaded",
    "csv_import.started",
    "csv_import.completed",
    "csv_import.cancelled",
    "content.sanitization.completed",
    "content.sanitization.blocked",
    "metrics.recalculation.requested",
    "metrics.snapshot.completed",
    "metrics.viewed",
    "ai.policy.changed",
    "knowledge.document.uploaded",
    "knowledge.version.approved",
    "knowledge.version.indexed",
    "knowledge.version.revoked",
    "knowledge.retrieval.completed",
    "analysis.requested",
    "analysis.completed",
    "analysis.blocked",
    "analysis.failed",
    "analysis.findings.viewed",
    "ai.budget.exceeded",
    "follow_up_task.created",
    "follow_up_task.assigned",
    "follow_up_task.priority_changed",
    "follow_up_task.due_date_changed",
    "follow_up_task.started",
    "follow_up_task.completed",
    "follow_up_task.cancelled",
    "follow_up_task.reopened",
    "follow_up_task.viewed",
    "conversation.list.viewed",
    "conversation.detail.viewed",
    "dashboard.viewed",
    "scorecard.viewed",
    "whatsapp.connection.created",
    "whatsapp.connection.verified",
    "whatsapp.connection.disabled",
    "webhook.rejected",
    "media.quarantined",
    "provider.templates.sync.completed",
    "provider.templates.sync.failed",
    "outbound_message.draft.created",
    "outbound_message.approved",
    "outbound_message.queued",
    "outbound_message.provider_accepted",
    "outbound_message.delivery_unknown",
    "outbound_message.delivery_failed",
    "whatsapp.reconciliation.completed",
)
_CRM_ACTION_VALUES = (
    "crm.connection.created",
    "crm.connection.updated",
    "crm.connection.verified",
    "crm.connection.disabled",
    "crm.field_mapping.changed",
    "crm.sync.completed",
    "crm.sync.failed",
    "crm.reconciliation.completed",
    "crm.conflict.resolved",
)
_ACTION_VALUES = _PREVIOUS_ACTION_VALUES + _CRM_ACTION_VALUES

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
    "encrypted_content",
    "outbox_job",
    "outbox_reconciliation",
    "webhook_event",
    "csv_import_batch",
    "content_sanitization",
    "metric_snapshot",
    "tenant_ai_policy",
    "ai_usage_daily",
    "analysis_run",
    "analysis_finding",
    "knowledge_document",
    "knowledge_document_version",
    "knowledge_chunk",
    "follow_up_task",
    "conversation_thread",
    "dashboard",
    "scorecard",
    "whatsapp_cloud_connection",
    "outbound_message",
    "provider_template",
    "provider_media_reference",
)
_CRM_TARGET_TYPE_VALUES = (
    "crm_connection",
    "crm_field_mapping",
    "crm_sync_attempt",
    "crm_conflict",
)
_TARGET_TYPE_VALUES = _PREVIOUS_TARGET_TYPE_VALUES + _CRM_TARGET_TYPE_VALUES

_PREVIOUS_CONTENT_KIND_VALUES = (
    "raw_message",
    "sanitized_message",
    "provider_payload",
    "outbound_message",
    "csv_import",
    "knowledge_document",
    "knowledge_chunk",
)
_CONTENT_KIND_VALUES = _PREVIOUS_CONTENT_KIND_VALUES + (
    "notification_payload",
    "provider_media_binary",
    "mfa_totp_secret",
)
_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
_CSV_IMPORT_MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
_KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES = 5 * 1024 * 1024
_KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES = 32 * 1024
_NOTIFICATION_PAYLOAD_MAX_PLAINTEXT_BYTES = 64 * 1024
_MFA_TOTP_SECRET_MAX_PLAINTEXT_BYTES = 64
_PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES = 100 * 1024 * 1024


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _upgrade_outbox_constraints() -> None:
    op.drop_constraint(op.f("ck_outbox_jobs_job_kind"), "outbox_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_jobs_job_kind"),
        "outbox_jobs",
        f"job_kind IN ({_quoted(_OUTBOX_JOB_KIND_VALUES)})",
    )


def _downgrade_outbox_constraints() -> None:
    op.drop_constraint(op.f("ck_outbox_jobs_job_kind"), "outbox_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_jobs_job_kind"),
        "outbox_jobs",
        f"job_kind IN ({_quoted(_PREVIOUS_OUTBOX_JOB_KIND_VALUES)})",
    )


def _upgrade_media_quarantine_constraints() -> None:
    op.drop_constraint(
        op.f("ck_provider_media_references_quarantine_status"),
        "provider_media_references",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_provider_media_references_quarantine_status"),
        "provider_media_references",
        f"quarantine_status IN ({_quoted(_MEDIA_QUARANTINE_VALUES)})",
    )


def _downgrade_media_quarantine_constraints() -> None:
    op.drop_constraint(
        op.f("ck_provider_media_references_quarantine_status"),
        "provider_media_references",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_provider_media_references_quarantine_status"),
        "provider_media_references",
        f"quarantine_status IN ({_quoted(_PREVIOUS_MEDIA_QUARANTINE_VALUES)})",
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
        "(kind = 'knowledge_document' "
        f"AND plaintext_byte_length <= {_KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'knowledge_chunk' "
        f"AND plaintext_byte_length <= {_KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'notification_payload' "
        f"AND plaintext_byte_length <= {_NOTIFICATION_PAYLOAD_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'mfa_totp_secret' "
        f"AND plaintext_byte_length <= {_MFA_TOTP_SECRET_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'provider_media_binary' "
        f"AND plaintext_byte_length <= {_PROVIDER_MEDIA_BINARY_MAX_PLAINTEXT_BYTES}) OR "
        "(kind IN ('raw_message', 'sanitized_message', 'outbound_message') "
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
        "(kind = 'csv_import' "
        f"AND plaintext_byte_length <= {_CSV_IMPORT_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'knowledge_document' "
        f"AND plaintext_byte_length <= {_KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES}) OR "
        "(kind = 'knowledge_chunk' "
        f"AND plaintext_byte_length <= {_KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES}) OR "
        "(kind IN ('raw_message', 'sanitized_message', 'outbound_message') "
        f"AND plaintext_byte_length <= {_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
    )


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
    _upgrade_outbox_constraints()
    _upgrade_media_quarantine_constraints()
    _upgrade_encrypted_content_constraints()
    _upgrade_audit_constraints()

    op.add_column(
        "provider_media_references",
        sa.Column("encrypted_content_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_provider_media_references_tenant_id_encrypted_content_id_encrypted_contents"),
        "provider_media_references",
        "encrypted_contents",
        ["tenant_id", "encrypted_content_id"],
        ["tenant_id", "id"],
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("recipient_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_payload_content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delivered_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN ({_quoted(_NOTIFICATION_KIND_VALUES)})", name="kind"),
        sa.CheckConstraint(f"status IN ({_quoted(_NOTIFICATION_STATUS_VALUES)})", name="status"),
        sa.CheckConstraint("template_version >= 1", name="template_version"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count"),
        sa.CheckConstraint(
            "("
            "(payload_tenant_id IS NULL AND encrypted_payload_content_id IS NULL) "
            "OR "
            "(payload_tenant_id IS NOT NULL AND encrypted_payload_content_id IS NOT NULL)"
            ")",
            name="payload_reference_pair",
        ),
        sa.ForeignKeyConstraint(
            ["payload_tenant_id", "encrypted_payload_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f(
                "fk_notification_deliveries_payload_tenant_id_encrypted_payload_content_id_encrypted_contents"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_notification_deliveries_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name=op.f("uq_notification_deliveries_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_notification_deliveries_tenant_status"),
        "notification_deliveries",
        ["tenant_id", "status"],
    )

    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number >= 1", name="attempt_number"),
        sa.CheckConstraint(
            f"outcome IN ({_quoted(_NOTIFICATION_ATTEMPT_OUTCOME_VALUES)})",
            name="outcome",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "delivery_id"],
            ["notification_deliveries.tenant_id", "notification_deliveries.id"],
            name=op.f(
                "fk_notification_delivery_attempts_tenant_id_delivery_id_notification_deliveries"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_delivery_attempts")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_notification_delivery_attempts_tenant_id_id")
        ),
    )
    op.create_index(
        op.f("ix_notification_delivery_attempts_delivery"),
        "notification_delivery_attempts",
        ["tenant_id", "delivery_id"],
    )

    op.create_table(
        "user_mfa_totp_enrollments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_secret_content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_accepted_timestep", sa.Integer(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_mfa_totp_enrollments_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["secret_tenant_id", "encrypted_secret_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f(
                "fk_user_mfa_totp_enrollments_secret_tenant_id_encrypted_secret_content_id_encrypted_contents"
            ),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_mfa_totp_enrollments")),
    )

    op.create_table(
        "legal_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("released_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("released_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_quoted(_LEGAL_HOLD_STATUS_VALUES)})", name="status"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_legal_holds_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_legal_holds")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_legal_holds_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_legal_holds_tenant_status"),
        "legal_holds",
        ["tenant_id", "status"],
    )

    op.create_table(
        "retention_purge_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("expires_before", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("items_scanned", sa.Integer(), nullable=False),
        sa.Column("items_deleted", sa.Integer(), nullable=False),
        sa.Column("items_skipped_legal_hold", sa.Integer(), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_quoted(_RETENTION_RUN_STATUS_VALUES)})", name="status"),
        sa.CheckConstraint("items_scanned >= 0", name="items_scanned"),
        sa.CheckConstraint("items_deleted >= 0", name="items_deleted"),
        sa.CheckConstraint("items_skipped_legal_hold >= 0", name="items_skipped_legal_hold"),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_retention_purge_runs_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retention_purge_runs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_retention_purge_runs_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_retention_purge_runs_tenant_created"),
        "retention_purge_runs",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "retention_purge_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purge_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"status IN ({_quoted(_RETENTION_BATCH_STATUS_VALUES)})",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purge_run_id"],
            ["retention_purge_runs.tenant_id", "retention_purge_runs.id"],
            name=op.f("fk_retention_purge_batches_tenant_id_purge_run_id_retention_purge_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retention_purge_batches")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_retention_purge_batches_tenant_id_id")
        ),
    )
    op.create_index(
        op.f("ix_retention_purge_batches_run"),
        "retention_purge_batches",
        ["tenant_id", "purge_run_id"],
    )

    op.create_table(
        "crm_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("portal_domain", sa.String(length=255), nullable=True),
        sa.Column("client_id_ref", sa.String(length=64), nullable=True),
        sa.Column("client_secret_ref", sa.String(length=64), nullable=True),
        sa.Column("access_token_ref", sa.String(length=64), nullable=True),
        sa.Column("refresh_token_ref", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_verified_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "last_successful_sync_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"provider IN ({_quoted(_CRM_PROVIDER_VALUES)})", name="provider"),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CRM_CONNECTION_STATUS_VALUES)})",
            name="status",
        ),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_crm_connections_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_connections")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_crm_connections_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "portal_domain",
            name=op.f("uq_crm_connections_tenant_id_provider_portal_domain"),
        ),
    )
    op.create_index(
        op.f("ix_crm_connections_tenant_status"),
        "crm_connections",
        ["tenant_id", "status"],
    )

    op.create_table(
        "crm_field_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_object_type", sa.String(length=64), nullable=False),
        sa.Column("external_field_key", sa.String(length=128), nullable=False),
        sa.Column("closeros_field", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CRM_MAPPING_STATUS_VALUES)})",
            name="status",
        ),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "crm_connection_id"],
            ["crm_connections.tenant_id", "crm_connections.id"],
            name=op.f("fk_crm_field_mappings_tenant_id_crm_connection_id_crm_connections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_field_mappings")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_crm_field_mappings_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "crm_connection_id",
            "external_object_type",
            "external_field_key",
            name=op.f("uq_crm_field_mappings_tenant_id_connection_object_field"),
        ),
    )
    op.create_index(
        op.f("ix_crm_field_mappings_tenant_connection"),
        "crm_field_mappings",
        ["tenant_id", "crm_connection_id"],
    )

    op.create_table(
        "crm_sync_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("cursor", sa.String(length=512), nullable=True),
        sa.Column("last_synced_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"direction IN ({_quoted(_CRM_SYNC_DIRECTION_VALUES)})",
            name="direction",
        ),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "crm_connection_id"],
            ["crm_connections.tenant_id", "crm_connections.id"],
            name=op.f("fk_crm_sync_checkpoints_tenant_id_crm_connection_id_crm_connections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_sync_checkpoints")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_crm_sync_checkpoints_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "crm_connection_id",
            "direction",
            "resource_type",
            name=op.f("uq_crm_sync_checkpoints_tenant_connection_direction_resource"),
        ),
    )

    op.create_table(
        "crm_sync_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_changed", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            f"direction IN ({_quoted(_CRM_SYNC_DIRECTION_VALUES)})",
            name="direction",
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CRM_ATTEMPT_STATUS_VALUES)})",
            name="status",
        ),
        sa.CheckConstraint("records_seen >= 0", name="records_seen"),
        sa.CheckConstraint("records_changed >= 0", name="records_changed"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "crm_connection_id"],
            ["crm_connections.tenant_id", "crm_connections.id"],
            name=op.f("fk_crm_sync_attempts_tenant_id_crm_connection_id_crm_connections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_sync_attempts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_crm_sync_attempts_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_crm_sync_attempts_tenant_connection_started"),
        "crm_sync_attempts",
        ["tenant_id", "crm_connection_id", "started_at"],
    )

    op.create_table(
        "crm_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_object_type", sa.String(length=64), nullable=False),
        sa.Column("external_object_id", sa.String(length=128), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("crm_value_hash", sa.String(length=64), nullable=False),
        sa.Column("closeros_value_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CRM_CONFLICT_STATUS_VALUES)})",
            name="status",
        ),
        sa.CheckConstraint(
            f"resolution IS NULL OR resolution IN ({_quoted(_CRM_CONFLICT_RESOLUTION_VALUES)})",
            name="resolution",
        ),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "crm_connection_id"],
            ["crm_connections.tenant_id", "crm_connections.id"],
            name=op.f("fk_crm_conflicts_tenant_id_crm_connection_id_crm_connections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_conflicts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_crm_conflicts_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "crm_connection_id",
            "external_object_type",
            "external_object_id",
            "field_key",
            "status",
            name=op.f("uq_crm_conflicts_tenant_connection_object_field_status"),
        ),
    )
    op.create_index(
        op.f("ix_crm_conflicts_tenant_connection_status"),
        "crm_conflicts",
        ["tenant_id", "crm_connection_id", "status"],
    )


def downgrade() -> None:
    _downgrade_audit_constraints()
    op.drop_table("crm_conflicts")
    op.drop_table("crm_sync_attempts")
    op.drop_table("crm_sync_checkpoints")
    op.drop_table("crm_field_mappings")
    op.drop_table("crm_connections")
    op.drop_table("retention_purge_batches")
    op.drop_table("retention_purge_runs")
    op.drop_table("legal_holds")
    op.drop_table("user_mfa_totp_enrollments")
    op.drop_table("notification_delivery_attempts")
    op.drop_table("notification_deliveries")

    op.drop_constraint(
        op.f("fk_provider_media_references_tenant_id_encrypted_content_id_encrypted_contents"),
        "provider_media_references",
        type_="foreignkey",
    )
    op.drop_column("provider_media_references", "encrypted_content_id")

    _downgrade_encrypted_content_constraints()
    _downgrade_media_quarantine_constraints()
    _downgrade_outbox_constraints()
