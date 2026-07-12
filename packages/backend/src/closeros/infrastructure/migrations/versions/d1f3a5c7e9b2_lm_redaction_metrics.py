"""LM redaction and metrics schema with audit/outbox extensions.

Revision ID: d1f3a5c7e9b2
Revises: f2a8c4e6b1d3
Create Date: 2026-07-12 17:30:00.000000

Creates ``content_sanitizations``, ``content_sanitization_category_counts``,
``metric_snapshots``, and ``metric_values`` with tenant-safe composite foreign
keys. Extends outbox job kind and audit CHECK constraints for LM redaction and
metrics actions.

Rollback / remediation
----------------------
The downgrade drops LM tables and restores prior CHECK constraints from the CSV
import (JK) migration. Safe only on an empty schema or in an isolated test
database. On populated production data:

- Rows referencing ``content_sanitization`` or ``metric_snapshot`` audit targets
  must be archived or migrated before constraint downgrade.
- Outbox jobs with ``job_kind = 'metrics.recalculate'`` must complete or be
  dead-lettered before downgrade.
- Use expand/migrate/contract for production rollback.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1f3a5c7e9b2"
down_revision: str | Sequence[str] | None = "f2a8c4e6b1d3"
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
)
_OUTBOX_JOB_KIND_VALUES = _PREVIOUS_OUTBOX_JOB_KIND_VALUES + ("metrics.recalculate",)

_JK_ACTION_VALUES = (
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
)

_JK_TARGET_TYPE_VALUES = (
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
)

_ACTION_VALUES = _JK_ACTION_VALUES + (
    "content.sanitization.completed",
    "content.sanitization.blocked",
    "metrics.recalculation.requested",
    "metrics.snapshot.completed",
    "metrics.viewed",
)

_TARGET_TYPE_VALUES = _JK_TARGET_TYPE_VALUES + (
    "content_sanitization",
    "metric_snapshot",
)

_SANITIZATION_STATUS_VALUES = ("pending", "completed", "failed")
_ANALYSIS_ELIGIBILITY_VALUES = ("eligible", "blocked", "not_applicable")
_SANITIZATION_FAILURE_CODE_VALUES = (
    "invalid_utf8",
    "control_content",
    "unresolved_restricted",
    "unsupported_encoding",
    "processing_failed",
)
_SOURCE_RESOURCE_TYPE_VALUES = ("message", "message_edit_event")
_SENSITIVE_DATA_CATEGORY_VALUES = (
    "email",
    "telephone",
    "payment_card",
    "iban",
    "national_id",
    "ip_address",
    "jwt",
    "bearer_token",
    "api_secret",
    "url_credential",
    "password_assignment",
    "control_content",
)

_METRIC_SCOPE_VALUES = ("tenant", "manager")
_METRIC_SNAPSHOT_STATUS_VALUES = ("pending", "completed", "failed")
_METRIC_KEY_VALUES = (
    "inbound_message_count",
    "outbound_manager_message_count",
    "active_thread_count",
    "inbound_thread_count",
    "responded_thread_count",
    "unresponded_thread_count",
    "response_rate_basis_points",
    "first_response_sample_count",
    "median_first_response_seconds",
    "p90_first_response_seconds",
    "failed_delivery_count",
    "appointment_booked_case_count",
    "won_case_count",
    "lost_case_count",
    "conversion_rate_basis_points",
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
        f"action IN ({_quoted(_JK_ACTION_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_audit_events_target_type"),
        "audit_events",
        f"target_type IN ({_quoted(_JK_TARGET_TYPE_VALUES)})",
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
    _upgrade_outbox_constraints()

    op.create_table(
        "content_sanitizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sanitized_content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_resource_type", sa.String(length=32), nullable=False),
        sa.Column("source_resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("detector_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("analysis_eligibility", sa.String(length=16), nullable=False),
        sa.Column("total_finding_count", sa.Integer(), nullable=False),
        sa.Column("critical_finding_count", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            f"source_resource_type IN ({_quoted(_SOURCE_RESOURCE_TYPE_VALUES)})",
            name=op.f("ck_content_sanitizations_source_resource_type"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_SANITIZATION_STATUS_VALUES)})",
            name=op.f("ck_content_sanitizations_status"),
        ),
        sa.CheckConstraint(
            f"analysis_eligibility IN ({_quoted(_ANALYSIS_ELIGIBILITY_VALUES)})",
            name=op.f("ck_content_sanitizations_analysis_eligibility"),
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            f"({_quoted(_SANITIZATION_FAILURE_CODE_VALUES)})",
            name=op.f("ck_content_sanitizations_failure_code"),
        ),
        sa.CheckConstraint(
            "total_finding_count >= 0",
            name=op.f("ck_content_sanitizations_total_finding_count_non_negative"),
        ),
        sa.CheckConstraint(
            "critical_finding_count >= 0 AND critical_finding_count <= total_finding_count",
            name=op.f("ck_content_sanitizations_critical_finding_count_bounds"),
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR status != 'completed'",
            name=op.f("ck_content_sanitizations_completed_at_required_for_completed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_content_sanitizations_tenant_id_source_content_id_encrypted_contents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sanitized_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_content_sanitizations_tenant_id_sanitized_content_id_encrypted_contents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_sanitizations")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_content_sanitizations_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "source_content_id",
            "policy_version",
            name=op.f("uq_content_sanitizations_tenant_source_policy"),
        ),
    )
    op.create_index(
        op.f("ix_content_sanitizations_tenant_created_at"),
        "content_sanitizations",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_sanitizations_tenant_source_content"),
        "content_sanitizations",
        ["tenant_id", "source_content_id"],
        unique=False,
    )

    op.create_table(
        "content_sanitization_category_counts",
        sa.Column("sanitization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            f"category IN ({_quoted(_SENSITIVE_DATA_CATEGORY_VALUES)})",
            name=op.f("ck_content_sanitization_category_counts_category"),
        ),
        sa.CheckConstraint(
            "count >= 1",
            name=op.f("ck_content_sanitization_category_counts_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sanitization_id"],
            ["content_sanitizations.tenant_id", "content_sanitizations.id"],
            name=op.f(
                "fk_content_sanitization_category_counts_tenant_id_sanitization_id_content_sanitizations"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "sanitization_id",
            "category",
            name=op.f("pk_content_sanitization_category_counts"),
        ),
    )
    op.create_index(
        op.f("ix_content_sanitization_category_counts_tenant_sanitization"),
        "content_sanitization_category_counts",
        ["tenant_id", "sanitization_id"],
        unique=False,
    )

    op.create_table(
        "metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("manager_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("window_start", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_code", sa.String(length=64), nullable=False),
        sa.Column("formula_version", sa.String(length=32), nullable=False),
        sa.Column("source_watermark", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("computed_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            f"scope IN ({_quoted(_METRIC_SCOPE_VALUES)})",
            name=op.f("ck_metric_snapshots_scope"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_METRIC_SNAPSHOT_STATUS_VALUES)})",
            name=op.f("ck_metric_snapshots_status"),
        ),
        sa.CheckConstraint(
            "window_end > window_start",
            name=op.f("ck_metric_snapshots_window_range_valid"),
        ),
        sa.CheckConstraint(
            "(scope = 'tenant' AND manager_user_id IS NULL) OR "
            "(scope = 'manager' AND manager_user_id IS NOT NULL)",
            name=op.f("ck_metric_snapshots_scope_manager_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_metric_snapshots_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_snapshots")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_metric_snapshots_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "scope",
            "manager_user_id",
            "window_start",
            "window_end",
            "formula_version",
            name=op.f("uq_metric_snapshots_identity"),
        ),
    )
    op.create_index(
        op.f("ix_metric_snapshots_tenant_computed_at"),
        "metric_snapshots",
        ["tenant_id", "computed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metric_snapshots_tenant_window"),
        "metric_snapshots",
        ["tenant_id", "window_start", "window_end"],
        unique=False,
    )

    op.create_table(
        "metric_values",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("numerator", sa.Integer(), nullable=True),
        sa.Column("denominator", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            f"metric_key IN ({_quoted(_METRIC_KEY_VALUES)})",
            name=op.f("ck_metric_values_metric_key"),
        ),
        sa.CheckConstraint(
            "value >= 0",
            name=op.f("ck_metric_values_value_non_negative"),
        ),
        sa.CheckConstraint(
            "numerator IS NULL OR numerator >= 0",
            name=op.f("ck_metric_values_numerator_non_negative"),
        ),
        sa.CheckConstraint(
            "denominator IS NULL OR denominator >= 0",
            name=op.f("ck_metric_values_denominator_non_negative"),
        ),
        sa.CheckConstraint(
            "(metric_key LIKE '%basis_points' AND value <= 10000) OR "
            "metric_key NOT LIKE '%basis_points'",
            name=op.f("ck_metric_values_basis_points_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["metric_snapshots.tenant_id", "metric_snapshots.id"],
            name=op.f("fk_metric_values_tenant_id_snapshot_id_metric_snapshots"),
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            "metric_key",
            name=op.f("pk_metric_values"),
        ),
    )
    op.create_index(
        op.f("ix_metric_values_tenant_snapshot"),
        "metric_values",
        ["tenant_id", "snapshot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_metric_values_tenant_snapshot"), table_name="metric_values")
    op.drop_table("metric_values")

    op.drop_index(op.f("ix_metric_snapshots_tenant_window"), table_name="metric_snapshots")
    op.drop_index(
        op.f("ix_metric_snapshots_tenant_computed_at"),
        table_name="metric_snapshots",
    )
    op.drop_table("metric_snapshots")

    op.drop_index(
        op.f("ix_content_sanitization_category_counts_tenant_sanitization"),
        table_name="content_sanitization_category_counts",
    )
    op.drop_table("content_sanitization_category_counts")

    op.drop_index(
        op.f("ix_content_sanitizations_tenant_source_content"),
        table_name="content_sanitizations",
    )
    op.drop_index(
        op.f("ix_content_sanitizations_tenant_created_at"),
        table_name="content_sanitizations",
    )
    op.drop_table("content_sanitizations")

    _downgrade_outbox_constraints()
    _downgrade_audit_constraints()
