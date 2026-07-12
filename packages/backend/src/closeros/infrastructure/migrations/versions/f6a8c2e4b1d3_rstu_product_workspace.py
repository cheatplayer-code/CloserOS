"""RSTU product workspace: follow-up tasks and dashboard query indexes.

Revision ID: f6a8c2e4b1d3
Revises: e3b7c9d1f5a2

Lock/backfill notes:
- ``follow_up_tasks`` creation uses a short ACCESS EXCLUSIVE lock on the new table only.
- Adding ``uq_memberships_tenant_id_id`` validates existing rows; safe because ``id`` is
  globally unique and tenant-scoped rows cannot collide.
- Dashboard indexes on ``conversation_threads`` and ``follow_up_tasks`` are created
  ``CONCURRENTLY``-free in this migration; expect brief SHARE lock on those tables during
  index build in production-sized datasets.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a8c2e4b1d3"
down_revision: str | Sequence[str] | None = "e3b7c9d1f5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
)

_RSTU_ACTION_VALUES = (
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

_RSTU_TARGET_TYPE_VALUES = (
    "follow_up_task",
    "conversation_thread",
    "dashboard",
    "scorecard",
)

_ACTION_VALUES = _PREVIOUS_ACTION_VALUES + _RSTU_ACTION_VALUES
_TARGET_TYPE_VALUES = _PREVIOUS_TARGET_TYPE_VALUES + _RSTU_TARGET_TYPE_VALUES

_TASK_STATUS_VALUES = ("open", "in_progress", "completed", "cancelled")
_TASK_PRIORITY_VALUES = ("low", "normal", "high", "urgent")


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

    op.create_unique_constraint(
        op.f("uq_memberships_tenant_id_id"),
        "memberships",
        ["tenant_id", "id"],
    )

    op.create_table(
        "follow_up_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_finding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("assigned_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_quoted(_TASK_STATUS_VALUES)})",
            name=op.f("ck_follow_up_tasks_status"),
        ),
        sa.CheckConstraint(
            f"priority IN ({_quoted(_TASK_PRIORITY_VALUES)})",
            name=op.f("ck_follow_up_tasks_priority"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_follow_up_tasks_version_positive")),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name=op.f("ck_follow_up_tasks_completed_at_consistency"),
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL)",
            name=op.f("ck_follow_up_tasks_cancelled_at_consistency"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_follow_up_tasks_updated_at_not_before_created_at"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "conversation_thread_id"),
            ("conversation_threads.tenant_id", "conversation_threads.id"),
            name=op.f("fk_follow_up_tasks_tenant_thread_conversation_threads"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "source_finding_id"),
            ("conversation_findings.tenant_id", "conversation_findings.id"),
            name=op.f("fk_follow_up_tasks_tenant_finding_conversation_findings"),
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "assigned_membership_id"),
            ("memberships.tenant_id", "memberships.id"),
            name=op.f("fk_follow_up_tasks_tenant_membership_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_follow_up_tasks")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_follow_up_tasks_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_follow_up_tasks_tenant_status_due_at"),
        "follow_up_tasks",
        ["tenant_id", "status", "due_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_follow_up_tasks_tenant_thread_id"),
        "follow_up_tasks",
        ["tenant_id", "conversation_thread_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_follow_up_tasks_tenant_assignee_status"),
        "follow_up_tasks",
        ["tenant_id", "assigned_membership_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_follow_up_tasks_tenant_updated_at_id"),
        "follow_up_tasks",
        ["tenant_id", "updated_at", "id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_conversation_threads_tenant_updated_at_id"),
        "conversation_threads",
        ["tenant_id", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_conversation_threads_tenant_updated_at_id"),
        table_name="conversation_threads",
    )
    op.drop_index(
        op.f("ix_follow_up_tasks_tenant_updated_at_id"),
        table_name="follow_up_tasks",
    )
    op.drop_index(
        op.f("ix_follow_up_tasks_tenant_assignee_status"),
        table_name="follow_up_tasks",
    )
    op.drop_index(
        op.f("ix_follow_up_tasks_tenant_thread_id"),
        table_name="follow_up_tasks",
    )
    op.drop_index(
        op.f("ix_follow_up_tasks_tenant_status_due_at"),
        table_name="follow_up_tasks",
    )
    op.drop_table("follow_up_tasks")
    op.drop_constraint(op.f("uq_memberships_tenant_id_id"), "memberships", type_="unique")
    _downgrade_audit_constraints()
