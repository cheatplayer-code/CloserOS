"""VW WhatsApp Cloud provider schema and constraint extensions.

Revision ID: b3d7f1a4c8e6
Revises: f6a8c2e4b1d3

Creates WhatsApp connection, template, media reference, outbound message, and
delivery attempt tables with tenant-safe composite foreign keys. Extends provider,
encrypted-content kind, outbox job kind, and audit CHECK constraints.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d7f1a4c8e6"
down_revision: str | Sequence[str] | None = "f6a8c2e4b1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
_CSV_IMPORT_MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
_KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES = 5 * 1024 * 1024
_KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES = 32 * 1024

_PREVIOUS_PROVIDER_VALUES = ("whatsapp", "instagram", "telegram_business", "synthetic")
_PROVIDER_VALUES = _PREVIOUS_PROVIDER_VALUES + ("whatsapp_cloud",)

_PREVIOUS_CONTENT_KIND_VALUES = (
    "raw_message",
    "sanitized_message",
    "provider_payload",
    "csv_import",
    "knowledge_document",
    "knowledge_chunk",
)
_CONTENT_KIND_VALUES = _PREVIOUS_CONTENT_KIND_VALUES + ("outbound_message",)

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
)
_OUTBOX_JOB_KIND_VALUES = _PREVIOUS_OUTBOX_JOB_KIND_VALUES + (
    "provider.message.send",
    "provider.templates.sync",
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
)

_VW_ACTION_VALUES = (
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

_VW_TARGET_TYPE_VALUES = (
    "whatsapp_cloud_connection",
    "outbound_message",
    "provider_template",
    "provider_media_reference",
)

_ACTION_VALUES = _PREVIOUS_ACTION_VALUES + _VW_ACTION_VALUES
_TARGET_TYPE_VALUES = _PREVIOUS_TARGET_TYPE_VALUES + _VW_TARGET_TYPE_VALUES

_CONNECTION_STATUS_VALUES = ("draft", "verification_pending", "active", "degraded", "disabled")
_WEBHOOK_SUBSCRIPTION_STATUS_VALUES = ("not_configured", "pending", "subscribed", "failed")
_TEMPLATE_APPROVAL_STATUS_VALUES = ("approved", "pending", "rejected", "paused", "disabled")
_MEDIA_QUARANTINE_STATUS_VALUES = (
    "quarantined_pending_scan",
    "scan_passed",
    "scan_failed",
    "fetch_unavailable",
)
_OUTBOUND_KIND_VALUES = ("free_form_text", "approved_template")
_OUTBOUND_STATUS_VALUES = (
    "draft",
    "pending_approval",
    "approved",
    "queued",
    "sending",
    "provider_accepted",
    "delivery_unknown",
    "delivered",
    "read",
    "failed",
    "cancelled",
)
_DELIVERY_ATTEMPT_OUTCOME_VALUES = ("succeeded", "failed", "delivery_unknown")


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
        "(kind IN ('raw_message', 'sanitized_message') "
        f"AND plaintext_byte_length <= {_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES})",
    )


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


def upgrade() -> None:
    _upgrade_audit_constraints()
    _upgrade_provider_constraints()
    _upgrade_encrypted_content_constraints()
    _upgrade_outbox_constraints()

    op.create_table(
        "whatsapp_cloud_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("display_phone_number", sa.String(length=32), nullable=True),
        sa.Column("graph_api_version", sa.String(length=16), nullable=False),
        sa.Column("access_token_ref", sa.String(length=64), nullable=True),
        sa.Column("app_secret_ref", sa.String(length=64), nullable=True),
        sa.Column("verify_token_ref", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("webhook_subscription_status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("webhook_public_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_verified_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "provider = 'whatsapp_cloud'", name=op.f("ck_whatsapp_cloud_connections_provider")
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CONNECTION_STATUS_VALUES)})",
            name=op.f("ck_whatsapp_cloud_connections_status"),
        ),
        sa.CheckConstraint(
            f"webhook_subscription_status IN ({_quoted(_WEBHOOK_SUBSCRIPTION_STATUS_VALUES)})",
            name=op.f("ck_whatsapp_cloud_connections_webhook_subscription_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_whatsapp_cloud_connections_version")),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'array'",
            name=op.f("ck_whatsapp_cloud_connections_capabilities_array"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f(
                "fk_whatsapp_cloud_connections_tenant_id_channel_connection_id_channel_connections"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_cloud_connections")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_whatsapp_cloud_connections_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "phone_number_id",
            name=op.f("uq_whatsapp_cloud_connections_tenant_id_phone_number_id"),
        ),
        sa.UniqueConstraint(
            "webhook_public_key",
            name=op.f("uq_whatsapp_cloud_connections_webhook_public_key"),
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_cloud_connections_tenant_id_status"),
        "whatsapp_cloud_connections",
        ["tenant_id", "status"],
    )

    op.create_table(
        "provider_message_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("whatsapp_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_template_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("approval_status", sa.String(length=16), nullable=False),
        sa.Column("component_shape", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parameter_count", sa.Integer(), nullable=False),
        sa.Column("last_synced_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"approval_status IN ({_quoted(_TEMPLATE_APPROVAL_STATUS_VALUES)})",
            name=op.f("ck_provider_message_templates_approval_status"),
        ),
        sa.CheckConstraint(
            "parameter_count >= 0", name=op.f("ck_provider_message_templates_parameter_count")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_provider_message_templates_version")),
        sa.CheckConstraint(
            "jsonb_typeof(component_shape) = 'array'",
            name=op.f("ck_provider_message_templates_component_shape_array"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "whatsapp_connection_id"],
            [
                "whatsapp_cloud_connections.tenant_id",
                "whatsapp_cloud_connections.id",
            ],
            name=op.f(
                "fk_provider_message_templates_tenant_id_whatsapp_connection_id_whatsapp_cloud_connections"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_message_templates")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_provider_message_templates_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "whatsapp_connection_id",
            "provider_template_id",
            name=op.f("uq_provider_message_templates_tenant_connection_provider_template_id"),
        ),
    )
    op.create_index(
        op.f("ix_provider_message_templates_tenant_connection_name"),
        "provider_message_templates",
        ["tenant_id", "whatsapp_connection_id", "name"],
    )

    op.create_table(
        "provider_media_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_media_id", sa.String(length=128), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("quarantine_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"quarantine_status IN ({_quoted(_MEDIA_QUARANTINE_STATUS_VALUES)})",
            name=op.f("ck_provider_media_references_quarantine_status"),
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name=op.f("ck_provider_media_references_size_bytes"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f(
                "fk_provider_media_references_tenant_id_channel_connection_id_channel_connections"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f(
                "fk_provider_media_references_tenant_id_conversation_thread_id_conversation_threads"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inbound_message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_provider_media_references_tenant_id_inbound_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_media_references")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_provider_media_references_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_connection_id",
            "provider_media_id",
            name=op.f("uq_provider_media_references_tenant_connection_provider_media_id"),
        ),
    )
    op.create_index(
        op.f("ix_provider_media_references_tenant_thread_id"),
        "provider_media_references",
        ["tenant_id", "conversation_thread_id"],
    )

    op.create_table(
        "outbound_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("encrypted_content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("approved_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("queued_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"kind IN ({_quoted(_OUTBOUND_KIND_VALUES)})",
            name=op.f("ck_outbound_messages_kind"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_OUTBOUND_STATUS_VALUES)})",
            name=op.f("ck_outbound_messages_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_outbound_messages_version")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f("fk_outbound_messages_tenant_id_conversation_thread_id_conversation_threads"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f("fk_outbound_messages_tenant_id_channel_connection_id_channel_connections"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "encrypted_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_outbound_messages_tenant_id_encrypted_content_id_encrypted_contents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_template_id"],
            ["provider_message_templates.tenant_id", "provider_message_templates.id"],
            name=op.f(
                "fk_outbound_messages_tenant_id_provider_template_id_provider_message_templates"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_messages")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_outbound_messages_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_outbound_messages_tenant_status_updated_at"),
        "outbound_messages",
        ["tenant_id", "status", "updated_at"],
    )
    op.create_index(
        op.f("ix_outbound_messages_tenant_thread_id"),
        "outbound_messages",
        ["tenant_id", "conversation_thread_id"],
    )

    op.create_table(
        "outbound_delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbound_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "attempt_number >= 1", name=op.f("ck_outbound_delivery_attempts_attempt_number")
        ),
        sa.CheckConstraint(
            f"outcome IN ({_quoted(_DELIVERY_ATTEMPT_OUTCOME_VALUES)})",
            name=op.f("ck_outbound_delivery_attempts_outcome"),
        ),
        sa.CheckConstraint(
            "finished_at >= started_at",
            name=op.f("ck_outbound_delivery_attempts_finished_at"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_message_id"],
            ["outbound_messages.tenant_id", "outbound_messages.id"],
            name=op.f(
                "fk_outbound_delivery_attempts_tenant_id_outbound_message_id_outbound_messages"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_delivery_attempts")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_outbound_delivery_attempts_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "outbound_message_id",
            "attempt_number",
            name=op.f("uq_outbound_delivery_attempts_tenant_message_attempt"),
        ),
    )


def downgrade() -> None:
    op.drop_table("outbound_delivery_attempts")
    op.drop_table("outbound_messages")
    op.drop_table("provider_media_references")
    op.drop_table("provider_message_templates")
    op.drop_table("whatsapp_cloud_connections")

    _downgrade_outbox_constraints()
    _downgrade_encrypted_content_constraints()
    _downgrade_provider_constraints()
    _downgrade_audit_constraints()
