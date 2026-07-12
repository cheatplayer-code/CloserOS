"""Platform tenant and canonical conversation persistence schema.

Revision ID: d4e8f1a2b3c5
Revises: 8e4b1d0f6a23
Create Date: 2026-07-12 13:35:00.000000

Creates tenant, membership, invitation, and canonical conversation tables with
tenant-safe composite foreign keys. Extends ``audit_events`` CHECK constraints
for platform lifecycle audit actions and target types.

Rollback / remediation
----------------------
The downgrade drops all platform tables in reverse dependency order and restores
the prior audit CHECK constraints. Safe only on an empty schema or in an
isolated test database. On populated production data, use expand/migrate/contract.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e8f1a2b3c5"
down_revision: str | Sequence[str] | None = "8e4b1d0f6a23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXTERNAL_ID_LENGTH = 256

_TENANT_STATUS_VALUES = ("active", "suspended")
_MEMBERSHIP_STATUS_VALUES = ("active", "suspended", "removed")
_INVITATION_STATUS_VALUES = ("pending", "accepted", "expired", "revoked")
_ROLE_VALUES = ("owner", "sales_head", "manager", "analyst", "compliance_admin")

_PROVIDER_VALUES = ("whatsapp", "instagram", "telegram_business")
_CHANNEL_CONNECTION_STATUS_VALUES = (
    "draft",
    "authorizing",
    "active",
    "degraded",
    "reauthorization_required",
    "revoked",
    "disconnected",
)
_LEAD_STATUS_VALUES = ("active", "merged", "archived")
_SALES_CASE_STATUS_VALUES = (
    "new",
    "awaiting_business",
    "awaiting_customer",
    "qualified",
    "appointment_proposed",
    "appointment_booked",
    "won",
    "lost",
    "closed_unknown",
)
_SENDER_TYPE_VALUES = ("customer", "bot", "manager", "system", "unknown")
_MESSAGE_DIRECTION_VALUES = ("inbound", "outbound")
_DELIVERY_STATUS_VALUES = ("pending", "sent", "delivered", "read", "failed", "unknown")
_CRM_OUTCOME_TYPE_VALUES = ("won", "lost", "cancelled", "unknown")
_WEBHOOK_PROCESSING_STATUS_VALUES = (
    "received",
    "acknowledged",
    "processing",
    "processed",
    "failed",
    "dead_letter",
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
)

_PREVIOUS_TARGET_TYPE_VALUES = (
    "user",
    "credential",
    "session",
    "tenant",
    "audit_log",
    "authentication",
)

_ACTION_VALUES = _PREVIOUS_ACTION_VALUES + (
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

_TARGET_TYPE_VALUES = _PREVIOUS_TARGET_TYPE_VALUES + (
    "membership",
    "invitation",
    "channel_connection",
    "manager_assignment",
)

_ADAPTER_METADATA_OBJECT_CHECK = "jsonb_typeof(adapter_metadata) = 'object'"
_SALES_CASE_STATUS_QUOTED = ", ".join(f"'{value}'" for value in _SALES_CASE_STATUS_VALUES)


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
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("time_zone", sa.Text(), nullable=False),
        sa.Column("raw_message_days", sa.Integer(), nullable=False),
        sa.Column("sanitized_message_days", sa.Integer(), nullable=False),
        sa.Column("ai_output_days", sa.Integer(), nullable=False),
        sa.Column("audit_log_days", sa.Integer(), nullable=False),
        sa.Column("backup_days", sa.Integer(), nullable=False),
        sa.Column("post_contract_deletion_days", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_TENANT_STATUS_VALUES)})",
            name=op.f("ck_tenants_status"),
        ),
        sa.CheckConstraint("raw_message_days >= 0", name=op.f("ck_tenants_raw_message_days")),
        sa.CheckConstraint(
            "sanitized_message_days >= 0",
            name=op.f("ck_tenants_sanitized_message_days"),
        ),
        sa.CheckConstraint("ai_output_days >= 0", name=op.f("ck_tenants_ai_output_days")),
        sa.CheckConstraint("audit_log_days >= 0", name=op.f("ck_tenants_audit_log_days")),
        sa.CheckConstraint("backup_days >= 0", name=op.f("ck_tenants_backup_days")),
        sa.CheckConstraint(
            "post_contract_deletion_days >= 0",
            name=op.f("ck_tenants_post_contract_deletion_days"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_index(op.f("ix_tenants_status"), "tenants", ["status"], unique=False)

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_MEMBERSHIP_STATUS_VALUES)})",
            name=op.f("ck_memberships_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_memberships_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("tenant_id", "user_id", name="tenant_id_user_id"),
    )
    op.create_index(op.f("ix_memberships_tenant_id"), "memberships", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_memberships_tenant_id_status"),
        "memberships",
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_table(
        "membership_roles",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            f"role IN ({_quoted(_ROLE_VALUES)})",
            name=op.f("ck_membership_roles_role"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_membership_roles_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("membership_id", "role", name="pk_membership_roles"),
    )
    op.create_index(
        op.f("ix_membership_roles_membership_id"),
        "membership_roles",
        ["membership_id"],
        unique=False,
    )

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_INVITATION_STATUS_VALUES)})",
            name=op.f("ck_invitations_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_invitations_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
    )
    op.create_index(
        op.f("ix_invitations_tenant_id"),
        "invitations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invitations_tenant_id_status"),
        "invitations",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invitations_expires_at"),
        "invitations",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "invitation_roles",
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            f"role IN ({_quoted(_ROLE_VALUES)})",
            name=op.f("ck_invitation_roles_role"),
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_invitation_roles_invitation_id_invitations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("invitation_id", "role", name="pk_invitation_roles"),
    )
    op.create_index(
        op.f("ix_invitation_roles_invitation_id"),
        "invitation_roles",
        ["invitation_id"],
        unique=False,
    )

    op.create_table(
        "channel_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_connection_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"provider IN ({_quoted(_PROVIDER_VALUES)})",
            name=op.f("ck_channel_connections_provider"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_CHANNEL_CONNECTION_STATUS_VALUES)})",
            name=op.f("ck_channel_connections_status"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_channel_connections_adapter_metadata_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_connections")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_channel_connections_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_connection_id",
            name=op.f("uq_channel_connections_tenant_id_provider_external_connection_id"),
        ),
    )
    op.create_index(
        op.f("ix_channel_connections_tenant_id"),
        "channel_connections",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_identity_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_LEAD_STATUS_VALUES)})",
            name=op.f("ck_leads_status"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_leads_adapter_metadata_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_leads_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_identity_id",
            name=op.f("uq_leads_tenant_id_external_identity_id"),
        ),
    )
    op.create_index(op.f("ix_leads_tenant_id"), "leads", ["tenant_id"], unique=False)

    op.create_table(
        "sales_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_SALES_CASE_STATUS_VALUES)})",
            name=op.f("ck_sales_cases_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_cases")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_sales_cases_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_sales_cases_tenant_id"),
        "sales_cases",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "conversation_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "external_conversation_id",
            sa.String(length=_EXTERNAL_ID_LENGTH),
            nullable=False,
        ),
        sa.Column("sales_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=True),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"lifecycle_status IS NULL OR lifecycle_status IN ({_SALES_CASE_STATUS_QUOTED})",
            name=op.f("ck_conversation_threads_lifecycle_status"),
        ),
        sa.CheckConstraint(
            "sales_case_id IS NULL OR lifecycle_status IS NULL",
            name=op.f("ck_conversation_threads_sales_case_lifecycle"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_conversation_threads_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f(
                "fk_conversation_threads_tenant_id_channel_connection_id_channel_connections"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
            name=op.f("fk_conversation_threads_tenant_id_sales_case_id_sales_cases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_threads")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_conversation_threads_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_connection_id",
            "external_conversation_id",
            name=op.f(
                "uq_conversation_threads_tenant_id_channel_connection_id_external_conversation_id"
            ),
        ),
    )
    op.create_index(
        op.f("ix_conversation_threads_tenant_id"),
        "conversation_threads",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_threads_tenant_id_channel_connection_id"),
        "conversation_threads",
        ["tenant_id", "channel_connection_id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_message_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("sender_type", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("received_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reply_to_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            f"sender_type IN ({_quoted(_SENDER_TYPE_VALUES)})",
            name=op.f("ck_messages_sender_type"),
        ),
        sa.CheckConstraint(
            f"direction IN ({_quoted(_MESSAGE_DIRECTION_VALUES)})",
            name=op.f("ck_messages_direction"),
        ),
        sa.CheckConstraint(
            "received_at >= sent_at",
            name=op.f("ck_messages_received_at_not_before_sent_at"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_messages_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f("fk_messages_tenant_id_conversation_thread_id_conversation_threads"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reply_to_message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_messages_tenant_id_reply_to_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_messages_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_thread_id",
            "external_message_id",
            name=op.f("uq_messages_tenant_id_conversation_thread_id_external_message_id"),
        ),
    )
    op.create_index(
        op.f("ix_messages_tenant_id_conversation_thread_id"),
        "messages",
        ["tenant_id", "conversation_thread_id"],
        unique=False,
    )

    op.create_table(
        "message_edit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_event_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_message_edit_events_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_message_edit_events_tenant_id_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_edit_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_event_id",
            name=op.f("uq_message_edit_events_tenant_id_external_event_id"),
        ),
    )
    op.create_index(
        op.f("ix_message_edit_events_tenant_id_message_id"),
        "message_edit_events",
        ["tenant_id", "message_id"],
        unique=False,
    )

    op.create_table(
        "message_deletion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_event_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_message_deletion_events_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_message_deletion_events_tenant_id_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_deletion_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_event_id",
            name=op.f("uq_message_deletion_events_tenant_id_external_event_id"),
        ),
    )
    op.create_index(
        op.f("ix_message_deletion_events_tenant_id_message_id"),
        "message_deletion_events",
        ["tenant_id", "message_id"],
        unique=False,
    )

    op.create_table(
        "message_delivery_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_event_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("delivery_status", sa.String(length=32), nullable=False),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            f"delivery_status IN ({_quoted(_DELIVERY_STATUS_VALUES)})",
            name=op.f("ck_message_delivery_status_events_delivery_status"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_message_delivery_status_events_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_message_delivery_status_events_tenant_id_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_delivery_status_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_event_id",
            name=op.f("uq_message_delivery_status_events_tenant_id_external_event_id"),
        ),
    )
    op.create_index(
        op.f("ix_message_delivery_status_events_tenant_id_message_id"),
        "message_delivery_status_events",
        ["tenant_id", "message_id"],
        unique=False,
    )

    op.create_table(
        "manager_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manager_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sales_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(conversation_thread_id IS NOT NULL AND sales_case_id IS NULL) OR "
            "(conversation_thread_id IS NULL AND sales_case_id IS NOT NULL)",
            name=op.f("ck_manager_assignments_assignment_target"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f(
                "fk_manager_assignments_tenant_id_conversation_thread_id_conversation_threads"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
            name=op.f("fk_manager_assignments_tenant_id_sales_case_id_sales_cases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manager_assignments")),
    )
    op.create_index(
        op.f("ix_manager_assignments_tenant_id"),
        "manager_assignments",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_manager_assignments_tenant_id_conversation_thread_id"),
        "manager_assignments",
        ["tenant_id", "conversation_thread_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_manager_assignments_tenant_id_sales_case_id"),
        "manager_assignments",
        ["tenant_id", "sales_case_id"],
        unique=False,
    )

    op.create_table(
        "crm_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sales_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_deal_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("outcome_type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            f"outcome_type IN ({_quoted(_CRM_OUTCOME_TYPE_VALUES)})",
            name=op.f("ck_crm_outcomes_outcome_type"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_crm_outcomes_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
            name=op.f("fk_crm_outcomes_tenant_id_sales_case_id_sales_cases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_outcomes")),
        sa.UniqueConstraint(
            "tenant_id",
            "external_deal_id",
            name=op.f("uq_crm_outcomes_tenant_id_external_deal_id"),
        ),
    )
    op.create_index(
        op.f("ix_crm_outcomes_tenant_id_sales_case_id"),
        "crm_outcomes",
        ["tenant_id", "sales_case_id"],
        unique=False,
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_event_id", sa.String(length=_EXTERNAL_ID_LENGTH), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("received_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("processed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("adapter_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            f"processing_status IN ({_quoted(_WEBHOOK_PROCESSING_STATUS_VALUES)})",
            name=op.f("ck_webhook_events_processing_status"),
        ),
        sa.CheckConstraint(
            "processed_at IS NULL OR processed_at >= received_at",
            name=op.f("ck_webhook_events_processed_at_not_before_received_at"),
        ),
        sa.CheckConstraint(
            _ADAPTER_METADATA_OBJECT_CHECK,
            name=op.f("ck_webhook_events_adapter_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name=op.f("fk_webhook_events_tenant_id_channel_connection_id_channel_connections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_connection_id",
            "external_event_id",
            name=op.f("uq_webhook_events_tenant_id_channel_connection_id_external_event_id"),
        ),
    )
    op.create_index(
        op.f("ix_webhook_events_tenant_id_channel_connection_id"),
        "webhook_events",
        ["tenant_id", "channel_connection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_webhook_events_tenant_id_channel_connection_id"),
        table_name="webhook_events",
    )
    op.drop_table("webhook_events")

    op.drop_index(
        op.f("ix_crm_outcomes_tenant_id_sales_case_id"),
        table_name="crm_outcomes",
    )
    op.drop_table("crm_outcomes")

    op.drop_index(
        op.f("ix_manager_assignments_tenant_id_sales_case_id"),
        table_name="manager_assignments",
    )
    op.drop_index(
        op.f("ix_manager_assignments_tenant_id_conversation_thread_id"),
        table_name="manager_assignments",
    )
    op.drop_index(op.f("ix_manager_assignments_tenant_id"), table_name="manager_assignments")
    op.drop_table("manager_assignments")

    op.drop_index(
        op.f("ix_message_delivery_status_events_tenant_id_message_id"),
        table_name="message_delivery_status_events",
    )
    op.drop_table("message_delivery_status_events")

    op.drop_index(
        op.f("ix_message_deletion_events_tenant_id_message_id"),
        table_name="message_deletion_events",
    )
    op.drop_table("message_deletion_events")

    op.drop_index(
        op.f("ix_message_edit_events_tenant_id_message_id"),
        table_name="message_edit_events",
    )
    op.drop_table("message_edit_events")

    op.drop_index(
        op.f("ix_messages_tenant_id_conversation_thread_id"),
        table_name="messages",
    )
    op.drop_table("messages")

    op.drop_index(
        op.f("ix_conversation_threads_tenant_id_channel_connection_id"),
        table_name="conversation_threads",
    )
    op.drop_index(op.f("ix_conversation_threads_tenant_id"), table_name="conversation_threads")
    op.drop_table("conversation_threads")

    op.drop_index(op.f("ix_sales_cases_tenant_id"), table_name="sales_cases")
    op.drop_table("sales_cases")

    op.drop_index(op.f("ix_leads_tenant_id"), table_name="leads")
    op.drop_table("leads")

    op.drop_index(op.f("ix_channel_connections_tenant_id"), table_name="channel_connections")
    op.drop_table("channel_connections")

    op.drop_index(
        op.f("ix_invitation_roles_invitation_id"),
        table_name="invitation_roles",
    )
    op.drop_table("invitation_roles")

    op.drop_index(op.f("ix_invitations_expires_at"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_tenant_id_status"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_tenant_id"), table_name="invitations")
    op.drop_table("invitations")

    op.drop_index(
        op.f("ix_membership_roles_membership_id"),
        table_name="membership_roles",
    )
    op.drop_table("membership_roles")

    op.drop_index(op.f("ix_memberships_tenant_id_status"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_tenant_id"), table_name="memberships")
    op.drop_table("memberships")

    op.drop_index(op.f("ix_tenants_status"), table_name="tenants")
    op.drop_table("tenants")

    _downgrade_audit_constraints()
