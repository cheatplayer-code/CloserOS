"""SQLAlchemy ORM models for transactional outbox persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.outbox import (
    OutboxAttemptOutcome,
    OutboxErrorCode,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxJobState,
)
from closeros.infrastructure.orm_base import Base

_JOB_KIND_VALUES = tuple(kind.value for kind in OutboxJobKind)
_JOB_STATE_VALUES = tuple(state.value for state in OutboxJobState)
_JOB_PHASE_VALUES = tuple(phase.value for phase in OutboxJobPhase)
_ATTEMPT_OUTCOME_VALUES = tuple(outcome.value for outcome in OutboxAttemptOutcome)
_ERROR_CODE_VALUES = tuple(code.value for code in OutboxErrorCode)


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class OutboxJobRow(Base):
    __tablename__ = "outbox_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    job_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    secondary_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    available_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"job_kind IN ({_quoted_values(_JOB_KIND_VALUES)})",
            name="job_kind",
        ),
        CheckConstraint(
            f"state IN ({_quoted_values(_JOB_STATE_VALUES)})",
            name="state",
        ),
        CheckConstraint(
            "priority >= 0 AND priority <= 1000",
            name="priority_bounds",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="attempt_count_non_negative",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="max_attempts_positive",
        ),
        CheckConstraint(
            "schema_version >= 1 AND schema_version <= 1000",
            name="schema_version_bounds",
        ),
        CheckConstraint(
            "version >= 1",
            name="version_positive",
        ),
        CheckConstraint(
            "deduplication_key ~ '^[a-z][a-z0-9_-]{0,127}$'",
            name="deduplication_key_format",
        ),
        CheckConstraint(
            "resource_type ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="resource_type_format",
        ),
        CheckConstraint(
            "claimed_by IS NULL OR claimed_by ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name="claimed_by_format",
        ),
        CheckConstraint(
            f"last_error_code IS NULL OR last_error_code IN ({_quoted_values(_ERROR_CODE_VALUES)})",
            name="last_error_code",
        ),
        CheckConstraint(
            "(job_kind = 'reconciliation.run' AND tenant_id IS NULL) OR "
            "(job_kind <> 'reconciliation.run' AND tenant_id IS NOT NULL)",
            name="tenant_scope",
        ),
        Index(
            "ix_outbox_jobs_state_available_at_priority",
            "state",
            "available_at",
            "priority",
        ),
        Index(
            "ix_outbox_jobs_claim_expires_at_state",
            "claim_expires_at",
            "state",
        ),
        Index(
            "ix_outbox_jobs_tenant_id_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_outbox_jobs_state_created_at",
            "state",
            "created_at",
        ),
        Index(
            "uq_outbox_jobs_tenant_id_deduplication_key",
            "tenant_id",
            "deduplication_key",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "uq_outbox_jobs_global_deduplication_key",
            "deduplication_key",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )


class OutboxJobAttemptRow(Base):
    __tablename__ = "outbox_job_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("outbox_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_token: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"phase IN ({_quoted_values(_JOB_PHASE_VALUES)})",
            name="phase",
        ),
        CheckConstraint(
            f"outcome IN ({_quoted_values(_ATTEMPT_OUTCOME_VALUES)})",
            name="outcome",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="attempt_number_positive",
        ),
        CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_quoted_values(_ERROR_CODE_VALUES)})",
            name="error_code",
        ),
        CheckConstraint(
            "finished_at >= started_at",
            name="finished_at_ordering",
        ),
        Index("ix_outbox_job_attempts_job_id_attempt_number", "job_id", "attempt_number"),
    )
