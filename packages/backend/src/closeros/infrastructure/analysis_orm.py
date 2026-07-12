"""SQLAlchemy ORM models for conversation analysis runs and findings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

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


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ConversationAnalysisRunRow(Base):
    __tablename__ = "conversation_analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    knowledge_context_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    output_digest: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    input_token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    output_token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "conversation_thread_id",
            "purpose",
            "prompt_version",
            "rubric_version",
            "input_digest",
            "knowledge_context_digest",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "conversation_thread_id"),
            ("conversation_threads.tenant_id", "conversation_threads.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "policy_id"),
            ("tenant_ai_policies.tenant_id", "tenant_ai_policies.id"),
        ),
        CheckConstraint(f"purpose IN ({_quoted(_ANALYSIS_PURPOSE_VALUES)})", name="purpose"),
        CheckConstraint(f"status IN ({_quoted(_ANALYSIS_STATUS_VALUES)})", name="status"),
        CheckConstraint(
            f"model_provider IN ({_quoted(_ANALYSIS_MODEL_PROVIDER_VALUES)})",
            name="model_provider",
        ),
        CheckConstraint("octet_length(input_digest) = 32", name="input_digest_length"),
        CheckConstraint(
            "octet_length(knowledge_context_digest) = 32",
            name="knowledge_context_digest_length",
        ),
        CheckConstraint(
            "output_digest IS NULL OR octet_length(output_digest) = 32",
            name="output_digest_length",
        ),
        CheckConstraint("input_token_count >= 0", name="input_token_count_non_negative"),
        CheckConstraint("output_token_count >= 0", name="output_token_count_non_negative"),
        CheckConstraint("cost_minor_units >= 0", name="cost_minor_units_non_negative"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= requested_at",
            name="completed_at_ordering",
        ),
        CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_quoted(_ANALYSIS_FAILURE_CODE_VALUES)})",
            name="failure_code",
        ),
        Index("ix_conversation_analysis_runs_tenant_requested_at", "tenant_id", "requested_at"),
        Index(
            "ix_conversation_analysis_runs_tenant_status_requested_at",
            "tenant_id",
            "status",
            "requested_at",
        ),
        Index(
            "ix_conversation_analysis_runs_tenant_thread_requested_at",
            "tenant_id",
            "conversation_thread_id",
            "requested_at",
        ),
    )


class ConversationFindingRow(Base):
    __tablename__ = "conversation_findings"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    finding_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_at_risk_basis_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ("tenant_id", "analysis_run_id"),
            ("conversation_analysis_runs.tenant_id", "conversation_analysis_runs.id"),
            ondelete="CASCADE",
        ),
        CheckConstraint(f"finding_code IN ({_quoted(_FINDING_CODE_VALUES)})", name="finding_code"),
        CheckConstraint(f"severity IN ({_quoted(_FINDING_SEVERITY_VALUES)})", name="severity"),
        CheckConstraint(f"status IN ({_quoted(_FINDING_STATUS_VALUES)})", name="status"),
        CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name="confidence_basis_points",
        ),
        CheckConstraint(
            "revenue_at_risk_basis_points IS NULL OR "
            "(revenue_at_risk_basis_points >= 0 AND revenue_at_risk_basis_points <= 10000)",
            name="revenue_at_risk_basis_points",
        ),
        CheckConstraint(
            "reviewed_at IS NULL OR reviewed_at >= created_at",
            name="reviewed_at_ordering",
        ),
        Index("ix_conversation_findings_tenant_analysis_run_id", "tenant_id", "analysis_run_id"),
        Index(
            "ix_conversation_findings_tenant_status_confidence",
            "tenant_id",
            "status",
            "confidence_basis_points",
        ),
    )


class ConversationFindingEvidenceRow(Base):
    __tablename__ = "conversation_finding_evidence"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    excerpt_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "finding_id", "message_id"),
        ForeignKeyConstraint(
            ("tenant_id", "finding_id"),
            ("conversation_findings.tenant_id", "conversation_findings.id"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "conversation_thread_id"),
            ("conversation_threads.tenant_id", "conversation_threads.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "message_id"),
            ("messages.tenant_id", "messages.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "excerpt_content_id"),
            ("encrypted_contents.tenant_id", "encrypted_contents.id"),
        ),
        Index("ix_conversation_finding_evidence_tenant_finding_id", "tenant_id", "finding_id"),
    )


class ConversationFindingKnowledgeCitationRow(Base):
    __tablename__ = "conversation_finding_knowledge_citations"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    retrieval_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "finding_id", "chunk_id"),
        ForeignKeyConstraint(
            ("tenant_id", "finding_id"),
            ("conversation_findings.tenant_id", "conversation_findings.id"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "document_id"),
            ("knowledge_documents.tenant_id", "knowledge_documents.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "document_version_id"),
            ("knowledge_document_versions.tenant_id", "knowledge_document_versions.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "chunk_id"),
            ("knowledge_chunks.tenant_id", "knowledge_chunks.id"),
        ),
        CheckConstraint("retrieval_rank >= 1", name="retrieval_rank_positive"),
        CheckConstraint(
            "relevance_basis_points >= 0 AND relevance_basis_points <= 10000",
            name="relevance_basis_points",
        ),
        Index(
            "ix_conversation_finding_knowledge_citations_tenant_finding_rank",
            "tenant_id",
            "finding_id",
            "retrieval_rank",
        ),
        Index(
            "ix_conversation_finding_knowledge_citations_tenant_chunk",
            "tenant_id",
            "chunk_id",
        ),
    )
