"""NOPQ AI policy, analysis, and knowledge retrieval schema.

Revision ID: e3b7c9d1f5a2
Revises: d1f3a5c7e9b2
Create Date: 2026-07-12 19:35:00.000000

Creates tenant AI policy, usage budget, conversation analysis, and knowledge-base
retrieval tables with tenant-safe composite foreign keys. Extends
``encrypted_contents`` kind and size CHECK constraints for encrypted knowledge
documents and chunks. Extends ``audit_events`` CHECK constraints for NOPQ
analysis and knowledge lifecycle actions.

Rollback / remediation
----------------------
The downgrade drops NOPQ tables in reverse dependency order and restores prior
LM-era ``audit_events`` and ``encrypted_contents`` CHECK constraints. Safe only
on an empty schema or in an isolated test database. On populated production
data, use expand/migrate/contract and archive dependent rows before rollback.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3b7c9d1f5a2"
down_revision: str | Sequence[str] | None = "d1f3a5c7e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CSV_IMPORT_MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
_RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES = 256 * 1024
_PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES = 1024 * 1024
_KNOWLEDGE_DOCUMENT_MAX_PLAINTEXT_BYTES = 5 * 1024 * 1024
_KNOWLEDGE_CHUNK_MAX_PLAINTEXT_BYTES = 32 * 1024

_PREVIOUS_CONTENT_KIND_VALUES = (
    "raw_message",
    "sanitized_message",
    "provider_payload",
    "csv_import",
)
_CONTENT_KIND_VALUES = _PREVIOUS_CONTENT_KIND_VALUES + ("knowledge_document", "knowledge_chunk")

_LM_ACTION_VALUES = (
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
)

_LM_TARGET_TYPE_VALUES = (
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
)

_NOPQ_ACTION_VALUES = (
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

_NOPQ_TARGET_TYPE_VALUES = (
    "tenant_ai_policy",
    "ai_usage_daily",
    "analysis_run",
    "analysis_finding",
    "knowledge_document",
    "knowledge_document_version",
    "knowledge_chunk",
)

_ACTION_VALUES = _LM_ACTION_VALUES + _NOPQ_ACTION_VALUES
_TARGET_TYPE_VALUES = _LM_TARGET_TYPE_VALUES + _NOPQ_TARGET_TYPE_VALUES

_ANALYSIS_PURPOSE_VALUES = ("risk_review", "coaching", "follow_up", "quality_control")
_ANALYSIS_STATUS_VALUES = ("requested", "completed", "blocked", "failed")
_ANALYSIS_FAILURE_CODE_VALUES = (
    "content_unavailable",
    "policy_blocked",
    "budget_exceeded",
    "provider_failed",
    "provider_timeout",
    "validation_failed",
)
_ANALYSIS_MODEL_PROVIDER_VALUES = ("deepseek", "openai", "anthropic", "local")

_FINDING_STATUS_VALUES = ("open", "accepted", "rejected", "corrected")
_FINDING_SEVERITY_VALUES = ("low", "medium", "high", "critical")
_FINDING_CODE_VALUES = (
    "missing_follow_up",
    "slow_response",
    "missing_next_step",
    "potential_loss_risk",
    "policy_violation",
)

_KNOWLEDGE_DOCUMENT_SOURCE_VALUES = ("upload", "import", "system_seed")
_KNOWLEDGE_DOCUMENT_STATUS_VALUES = ("active", "archived", "deleted")
_KNOWLEDGE_VERSION_STATUS_VALUES = ("draft", "approved", "indexed", "revoked", "superseded")
_KNOWLEDGE_CHUNK_STATUS_VALUES = ("active", "revoked")

_POLICY_MODE_VALUES = ("off", "observe", "enforce")
_USAGE_DIMENSION_VALUES = ("analysis", "retrieval")


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
        f"action IN ({_quoted(_LM_ACTION_VALUES)})",
    )
    op.create_check_constraint(
        op.f("ck_audit_events_target_type"),
        "audit_events",
        f"target_type IN ({_quoted(_LM_TARGET_TYPE_VALUES)})",
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
        "(kind IN ('raw_message', 'sanitized_message') "
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


def upgrade() -> None:
    _upgrade_audit_constraints()
    _upgrade_encrypted_content_constraints()

    op.create_table(
        "tenant_ai_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("minimum_confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("daily_budget_limit_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("monthly_budget_limit_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"mode IN ({_quoted(_POLICY_MODE_VALUES)})",
            name=op.f("ck_tenant_ai_policies_mode"),
        ),
        sa.CheckConstraint(
            "minimum_confidence_basis_points >= 0 AND minimum_confidence_basis_points <= 10000",
            name=op.f("ck_tenant_ai_policies_minimum_confidence_basis_points"),
        ),
        sa.CheckConstraint(
            "daily_budget_limit_minor_units >= 0",
            name=op.f("ck_tenant_ai_policies_daily_budget_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "monthly_budget_limit_minor_units >= 0",
            name=op.f("ck_tenant_ai_policies_monthly_budget_limit_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_ai_policies_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_ai_policies")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_tenant_ai_policies_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_tenant_ai_policies_tenant_id")),
    )
    op.create_index(
        op.f("ix_tenant_ai_policies_tenant_id_updated_at"),
        "tenant_ai_policies",
        ["tenant_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "ai_usage_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(length=16), nullable=False),
        sa.Column("model_provider", sa.String(length=32), nullable=False),
        sa.Column("input_token_count", sa.Integer(), nullable=False),
        sa.Column("output_token_count", sa.Integer(), nullable=False),
        sa.Column("requests_count", sa.Integer(), nullable=False),
        sa.Column("cost_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("budget_limit_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("budget_consumed_basis_points", sa.Integer(), nullable=False),
        sa.Column("last_recorded_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"dimension IN ({_quoted(_USAGE_DIMENSION_VALUES)})",
            name=op.f("ck_ai_usage_daily_dimension"),
        ),
        sa.CheckConstraint(
            f"model_provider IN ({_quoted(_ANALYSIS_MODEL_PROVIDER_VALUES)})",
            name=op.f("ck_ai_usage_daily_model_provider"),
        ),
        sa.CheckConstraint(
            "input_token_count >= 0",
            name=op.f("ck_ai_usage_daily_input_token_count_non_negative"),
        ),
        sa.CheckConstraint(
            "output_token_count >= 0",
            name=op.f("ck_ai_usage_daily_output_token_count_non_negative"),
        ),
        sa.CheckConstraint(
            "requests_count >= 0",
            name=op.f("ck_ai_usage_daily_requests_count_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_minor_units >= 0",
            name=op.f("ck_ai_usage_daily_cost_minor_units_non_negative"),
        ),
        sa.CheckConstraint(
            "budget_limit_minor_units >= 0",
            name=op.f("ck_ai_usage_daily_budget_limit_minor_units_non_negative"),
        ),
        sa.CheckConstraint(
            "budget_consumed_basis_points >= 0 AND budget_consumed_basis_points <= 10000",
            name=op.f("ck_ai_usage_daily_budget_consumed_basis_points"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_usage_daily_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_daily")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_ai_usage_daily_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "usage_date",
            "dimension",
            "model_provider",
            name=op.f("uq_ai_usage_daily_tenant_usage_dimension_provider"),
        ),
    )
    op.create_index(
        op.f("ix_ai_usage_daily_tenant_usage_date"),
        "ai_usage_daily",
        ["tenant_id", "usage_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_usage_daily_tenant_budget_bps"),
        "ai_usage_daily",
        ["tenant_id", "budget_consumed_basis_points", "usage_date"],
        unique=False,
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("external_reference", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"source_type IN ({_quoted(_KNOWLEDGE_DOCUMENT_SOURCE_VALUES)})",
            name=op.f("ck_knowledge_documents_source_type"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_KNOWLEDGE_DOCUMENT_STATUS_VALUES)})",
            name=op.f("ck_knowledge_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_documents_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_knowledge_documents_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_knowledge_documents_tenant_status_updated_at"),
        "knowledge_documents",
        ["tenant_id", "status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_sha256_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("effective_from", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("effective_to", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("approved_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("indexed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version_number >= 1",
            name=op.f("ck_knowledge_document_versions_version_number_positive"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_KNOWLEDGE_VERSION_STATUS_VALUES)})",
            name=op.f("ck_knowledge_document_versions_status"),
        ),
        sa.CheckConstraint(
            "octet_length(content_sha256_digest) = 32",
            name=op.f("ck_knowledge_document_versions_content_sha256_digest_length"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_knowledge_document_versions_effective_window"),
        ),
        sa.CheckConstraint(
            (
                "(status IN ('approved', 'indexed', 'revoked', 'superseded') "
                "AND approved_at IS NOT NULL) OR status IN ('draft')"
            ),
            name=op.f("ck_knowledge_document_versions_approved_at_required"),
        ),
        sa.CheckConstraint(
            "(status = 'indexed' AND indexed_at IS NOT NULL) OR status <> 'indexed'",
            name=op.f("ck_knowledge_document_versions_indexed_at_required"),
        ),
        sa.CheckConstraint(
            "(status = 'revoked' AND revoked_at IS NOT NULL) OR status <> 'revoked'",
            name=op.f("ck_knowledge_document_versions_revoked_at_required"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name=op.f("fk_knowledge_document_versions_tenant_id_document_id_knowledge_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_knowledge_document_versions_tenant_id_content_id_encrypted_contents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_document_versions")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_knowledge_document_versions_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "version_number",
            name=op.f("uq_knowledge_document_versions_tenant_document_version_number"),
        ),
    )
    op.create_index(
        op.f("ix_knowledge_document_versions_tenant_status_effective_from"),
        "knowledge_document_versions",
        ["tenant_id", "status", "effective_from"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_document_versions_tenant_document_status"),
        "knowledge_document_versions",
        ["tenant_id", "document_id", "status"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("chunk_sha256_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_knowledge_chunks_position_non_negative"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_KNOWLEDGE_CHUNK_STATUS_VALUES)})",
            name=op.f("ck_knowledge_chunks_status"),
        ),
        sa.CheckConstraint(
            "octet_length(chunk_sha256_digest) = 32",
            name=op.f("ck_knowledge_chunks_chunk_sha256_digest_length"),
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name=op.f("ck_knowledge_chunks_token_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            name=op.f(
                "fk_knowledge_chunks_tenant_id_document_version_id_knowledge_document_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f("fk_knowledge_chunks_tenant_id_content_id_encrypted_contents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_knowledge_chunks_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "position",
            name=op.f("uq_knowledge_chunks_tenant_document_version_position"),
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_tenant_document_version_status"),
        "knowledge_chunks",
        ["tenant_id", "document_version_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chunks_tenant_chunk_sha256_digest"),
        "knowledge_chunks",
        ["tenant_id", "chunk_sha256_digest"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunk_terms",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("weight_basis_points", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "octet_length(term_digest) = 32",
            name=op.f("ck_knowledge_chunk_terms_term_digest_length"),
        ),
        sa.CheckConstraint(
            "weight_basis_points >= 0 AND weight_basis_points <= 10000",
            name=op.f("ck_knowledge_chunk_terms_weight_basis_points"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.id"],
            name=op.f("fk_knowledge_chunk_terms_tenant_id_chunk_id_knowledge_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "chunk_id",
            "term_digest",
            name=op.f("pk_knowledge_chunk_terms"),
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunk_terms_tenant_term_digest"),
        "knowledge_chunk_terms",
        ["tenant_id", "term_digest"],
        unique=False,
    )

    op.create_table(
        "conversation_analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("input_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("knowledge_context_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("output_digest", postgresql.BYTEA(), nullable=True),
        sa.Column("model_provider", sa.String(length=32), nullable=False),
        sa.Column("input_token_count", sa.Integer(), nullable=False),
        sa.Column("output_token_count", sa.Integer(), nullable=False),
        sa.Column("cost_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("requested_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            f"purpose IN ({_quoted(_ANALYSIS_PURPOSE_VALUES)})",
            name=op.f("ck_conversation_analysis_runs_purpose"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_ANALYSIS_STATUS_VALUES)})",
            name=op.f("ck_conversation_analysis_runs_status"),
        ),
        sa.CheckConstraint(
            f"model_provider IN ({_quoted(_ANALYSIS_MODEL_PROVIDER_VALUES)})",
            name=op.f("ck_conversation_analysis_runs_model_provider"),
        ),
        sa.CheckConstraint(
            "octet_length(input_digest) = 32",
            name=op.f("ck_conversation_analysis_runs_input_digest_length"),
        ),
        sa.CheckConstraint(
            "octet_length(knowledge_context_digest) = 32",
            name=op.f("ck_conversation_analysis_runs_knowledge_context_digest_length"),
        ),
        sa.CheckConstraint(
            "output_digest IS NULL OR octet_length(output_digest) = 32",
            name=op.f("ck_conversation_analysis_runs_output_digest_length"),
        ),
        sa.CheckConstraint(
            "input_token_count >= 0",
            name=op.f("ck_conversation_analysis_runs_input_token_count_non_negative"),
        ),
        sa.CheckConstraint(
            "output_token_count >= 0",
            name=op.f("ck_conversation_analysis_runs_output_token_count_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_minor_units >= 0",
            name=op.f("ck_conversation_analysis_runs_cost_minor_units_non_negative"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= requested_at",
            name=op.f("ck_conversation_analysis_runs_completed_at_ordering"),
        ),
        sa.CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_quoted(_ANALYSIS_FAILURE_CODE_VALUES)})",
            name=op.f("ck_conversation_analysis_runs_failure_code"),
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND output_digest IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status = 'blocked' AND completed_at IS NOT NULL) OR "
            "(status = 'failed' AND failure_code IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status = 'requested' AND completed_at IS NULL)",
            name=op.f("ck_conversation_analysis_runs_status_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f(
                "fk_conversation_analysis_runs_tenant_id_conversation_thread_id_conversation_threads"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_id"],
            ["tenant_ai_policies.tenant_id", "tenant_ai_policies.id"],
            name=op.f("fk_conversation_analysis_runs_tenant_id_policy_id_tenant_ai_policies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_analysis_runs")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_conversation_analysis_runs_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_thread_id",
            "purpose",
            "prompt_version",
            "rubric_version",
            "input_digest",
            "knowledge_context_digest",
            name=op.f("uq_conversation_analysis_runs_idempotency"),
        ),
    )
    op.create_index(
        op.f("ix_conversation_analysis_runs_tenant_requested_at"),
        "conversation_analysis_runs",
        ["tenant_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_analysis_runs_tenant_status_requested_at"),
        "conversation_analysis_runs",
        ["tenant_id", "status", "requested_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_analysis_runs_tenant_thread_requested_at"),
        "conversation_analysis_runs",
        ["tenant_id", "conversation_thread_id", "requested_at"],
        unique=False,
    )

    op.create_table(
        "conversation_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("revenue_at_risk_basis_points", sa.Integer(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reviewed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"finding_code IN ({_quoted(_FINDING_CODE_VALUES)})",
            name=op.f("ck_conversation_findings_finding_code"),
        ),
        sa.CheckConstraint(
            f"severity IN ({_quoted(_FINDING_SEVERITY_VALUES)})",
            name=op.f("ck_conversation_findings_severity"),
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(_FINDING_STATUS_VALUES)})",
            name=op.f("ck_conversation_findings_status"),
        ),
        sa.CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name=op.f("ck_conversation_findings_confidence_basis_points"),
        ),
        sa.CheckConstraint(
            "revenue_at_risk_basis_points IS NULL OR "
            "(revenue_at_risk_basis_points >= 0 AND revenue_at_risk_basis_points <= 10000)",
            name=op.f("ck_conversation_findings_revenue_at_risk_basis_points"),
        ),
        sa.CheckConstraint(
            "reviewed_at IS NULL OR reviewed_at >= created_at",
            name=op.f("ck_conversation_findings_reviewed_at_ordering"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["conversation_analysis_runs.tenant_id", "conversation_analysis_runs.id"],
            name=op.f(
                "fk_conversation_findings_tenant_id_analysis_run_id_conversation_analysis_runs"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_findings")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_conversation_findings_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_conversation_findings_tenant_analysis_run_id"),
        "conversation_findings",
        ["tenant_id", "analysis_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_findings_tenant_status_confidence"),
        "conversation_findings",
        ["tenant_id", "status", "confidence_basis_points"],
        unique=False,
    )

    op.create_table(
        "conversation_finding_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("excerpt_content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["conversation_findings.tenant_id", "conversation_findings.id"],
            name=op.f(
                "fk_conversation_finding_evidence_tenant_id_finding_id_conversation_findings"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f(
                "fk_conversation_finding_evidence_tenant_id_conversation_thread_id_conversation_threads"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name=op.f("fk_conversation_finding_evidence_tenant_id_message_id_messages"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "excerpt_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            name=op.f(
                "fk_conversation_finding_evidence_tenant_id_excerpt_content_id_encrypted_contents"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_finding_evidence")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_conversation_finding_evidence_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "finding_id",
            "message_id",
            name=op.f("uq_conversation_finding_evidence_tenant_finding_message"),
        ),
    )
    op.create_index(
        op.f("ix_conversation_finding_evidence_tenant_finding_id"),
        "conversation_finding_evidence",
        ["tenant_id", "finding_id"],
        unique=False,
    )

    op.create_table(
        "conversation_finding_knowledge_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("relevance_basis_points", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "retrieval_rank >= 1",
            name=op.f("ck_conversation_finding_knowledge_citations_retrieval_rank_positive"),
        ),
        sa.CheckConstraint(
            "relevance_basis_points >= 0 AND relevance_basis_points <= 10000",
            name=op.f("ck_conversation_finding_knowledge_citations_relevance_basis_points"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["conversation_findings.tenant_id", "conversation_findings.id"],
            name=op.f(
                "fk_conversation_finding_knowledge_citations_tenant_id_finding_id_conversation_findings"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name=op.f(
                "fk_conversation_finding_knowledge_citations_tenant_id_document_id_knowledge_documents"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            name=op.f(
                "fk_conversation_finding_knowledge_citations_tenant_id_document_version_id_knowledge_document_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.id"],
            name=op.f(
                "fk_conversation_finding_knowledge_citations_tenant_id_chunk_id_knowledge_chunks"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_conversation_finding_knowledge_citations"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_conversation_finding_knowledge_citations_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "finding_id",
            "chunk_id",
            name=op.f("uq_conversation_finding_knowledge_citations_tenant_finding_chunk"),
        ),
    )
    op.create_index(
        op.f("ix_conversation_finding_knowledge_citations_tenant_finding_rank"),
        "conversation_finding_knowledge_citations",
        ["tenant_id", "finding_id", "retrieval_rank"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_finding_knowledge_citations_tenant_chunk"),
        "conversation_finding_knowledge_citations",
        ["tenant_id", "chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_conversation_finding_knowledge_citations_tenant_chunk"),
        table_name="conversation_finding_knowledge_citations",
    )
    op.drop_index(
        op.f("ix_conversation_finding_knowledge_citations_tenant_finding_rank"),
        table_name="conversation_finding_knowledge_citations",
    )
    op.drop_table("conversation_finding_knowledge_citations")

    op.drop_index(
        op.f("ix_conversation_finding_evidence_tenant_finding_id"),
        table_name="conversation_finding_evidence",
    )
    op.drop_table("conversation_finding_evidence")

    op.drop_index(
        op.f("ix_conversation_findings_tenant_status_confidence"),
        table_name="conversation_findings",
    )
    op.drop_index(
        op.f("ix_conversation_findings_tenant_analysis_run_id"),
        table_name="conversation_findings",
    )
    op.drop_table("conversation_findings")

    op.drop_index(
        op.f("ix_conversation_analysis_runs_tenant_thread_requested_at"),
        table_name="conversation_analysis_runs",
    )
    op.drop_index(
        op.f("ix_conversation_analysis_runs_tenant_status_requested_at"),
        table_name="conversation_analysis_runs",
    )
    op.drop_index(
        op.f("ix_conversation_analysis_runs_tenant_requested_at"),
        table_name="conversation_analysis_runs",
    )
    op.drop_table("conversation_analysis_runs")

    op.drop_index(
        op.f("ix_knowledge_chunk_terms_tenant_term_digest"),
        table_name="knowledge_chunk_terms",
    )
    op.drop_table("knowledge_chunk_terms")

    op.drop_index(
        op.f("ix_knowledge_chunks_tenant_chunk_sha256_digest"),
        table_name="knowledge_chunks",
    )
    op.drop_index(
        op.f("ix_knowledge_chunks_tenant_document_version_status"),
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")

    op.drop_index(
        op.f("ix_knowledge_document_versions_tenant_document_status"),
        table_name="knowledge_document_versions",
    )
    op.drop_index(
        op.f("ix_knowledge_document_versions_tenant_status_effective_from"),
        table_name="knowledge_document_versions",
    )
    op.drop_table("knowledge_document_versions")

    op.drop_index(
        op.f("ix_knowledge_documents_tenant_status_updated_at"),
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")

    op.drop_index(
        op.f("ix_ai_usage_daily_tenant_budget_bps"),
        table_name="ai_usage_daily",
    )
    op.drop_index(
        op.f("ix_ai_usage_daily_tenant_usage_date"),
        table_name="ai_usage_daily",
    )
    op.drop_table("ai_usage_daily")

    op.drop_index(
        op.f("ix_tenant_ai_policies_tenant_id_updated_at"),
        table_name="tenant_ai_policies",
    )
    op.drop_table("tenant_ai_policies")

    _downgrade_encrypted_content_constraints()
    _downgrade_audit_constraints()
