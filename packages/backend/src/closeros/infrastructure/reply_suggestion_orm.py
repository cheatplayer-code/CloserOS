"""SQLAlchemy ORM for reply suggestions and buyer memory (Block V1-3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_RUN_STATUS = ("pending", "running", "completed", "blocked", "failed", "expired")
_CANDIDATE_KEYS = ("recommended", "concise", "consultative", "confident")
_EVENT_TYPES = (
    "requested",
    "generated",
    "blocked",
    "shown",
    "selected",
    "edited",
    "rejected",
    "draft_created",
    "approved",
    "sent",
    "customer_replied",
    "booked",
    "won",
    "lost",
)
_COST_STATUS = ("unknown", "known", "not_applicable")
_FACT_TYPES = (
    "preferred_language",
    "budget_min",
    "budget_max",
    "currency",
    "preferred_category",
    "preferred_color",
    "preferred_material",
    "dimension_requirement",
    "location",
    "purchase_timeline",
    "product_interest",
    "objection",
    "contact_time_preference",
    "seller_promise",
    "customer_requested_follow_up",
)
_FACT_STATUS = ("inferred", "confirmed", "rejected", "expired", "deleted")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ReplySuggestionRunRow(Base):
    __tablename__ = "reply_suggestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_milliseconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_status: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_cost_microunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    next_best_action_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_digest: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    output_digest: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        ForeignKeyConstraint(
            ("tenant_id", "conversation_thread_id"),
            ("conversation_threads.tenant_id", "conversation_threads.id"),
        ),
        CheckConstraint(f"status IN ({_quoted(_RUN_STATUS)})", name="status"),
        CheckConstraint(f"cost_status IN ({_quoted(_COST_STATUS)})", name="cost_status"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(cost_status <> 'known') OR (estimated_cost_microunits IS NOT NULL)",
            name="known_cost_requires_amount",
        ),
        CheckConstraint(
            "(cost_status <> 'unknown') OR (estimated_cost_microunits IS NULL)",
            name="unknown_cost_null_amount",
        ),
        Index(
            "ix_reply_suggestion_runs_tenant_thread_created",
            "tenant_id",
            "conversation_thread_id",
            "created_at",
        ),
    )


class ReplySuggestionCandidateRow(Base):
    __tablename__ = "reply_suggestion_candidates"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_message_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    product_references: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    knowledge_citation_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "run_id", "candidate_key"),
        ForeignKeyConstraint(
            ("tenant_id", "run_id"),
            ("reply_suggestion_runs.tenant_id", "reply_suggestion_runs.id"),
        ),
        CheckConstraint(f"candidate_key IN ({_quoted(_CANDIDATE_KEYS)})", name="candidate_key"),
        CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name="confidence_range",
        ),
        Index("ix_reply_suggestion_candidates_tenant_run", "tenant_id", "run_id"),
    )


class ReplySuggestionEventRow(Base):
    __tablename__ = "reply_suggestion_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ("tenant_id", "run_id"),
            ("reply_suggestion_runs.tenant_id", "reply_suggestion_runs.id"),
        ),
        CheckConstraint(f"event_type IN ({_quoted(_EVENT_TYPES)})", name="event_type"),
        Index("ix_reply_suggestion_events_tenant_run", "tenant_id", "run_id", "occurred_at"),
    )


class BuyerMemoryFactRow(Base):
    __tablename__ = "buyer_memory_facts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    display_value: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    supersedes_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ("tenant_id", "conversation_thread_id"),
            ("conversation_threads.tenant_id", "conversation_threads.id"),
        ),
        CheckConstraint(f"fact_type IN ({_quoted(_FACT_TYPES)})", name="fact_type"),
        CheckConstraint(f"status IN ({_quoted(_FACT_STATUS)})", name="status"),
        CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name="confidence_range",
        ),
        CheckConstraint(
            "(status <> 'confirmed') OR (source_message_id IS NOT NULL)",
            name="confirmed_requires_source",
        ),
        CheckConstraint(
            "(status <> 'inferred') OR (expires_at IS NOT NULL)",
            name="inferred_requires_expiry",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_buyer_memory_facts_tenant_thread_type",
            "tenant_id",
            "conversation_thread_id",
            "fact_type",
        ),
        Index("ix_buyer_memory_facts_tenant_lead", "tenant_id", "lead_id"),
    )
