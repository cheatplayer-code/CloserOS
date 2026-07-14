"""Alembic revision: V1 reply suggestion copilot and buyer memory.

Revision ID: c3e5a7b9d1f0
Revises: b2d4f6a8c0e1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3e5a7b9d1f0"
down_revision: str | Sequence[str] | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN = "('pending', 'running', 'completed', 'blocked', 'failed', 'expired')"
_KEYS = "('recommended', 'concise', 'consultative', 'confident')"
_EVENTS = (
    "('requested', 'generated', 'blocked', 'shown', 'selected', 'edited', 'rejected', "
    "'draft_created', 'approved', 'sent', 'customer_replied', 'booked', 'won', 'lost')"
)
_COST = "('unknown', 'known', 'not_applicable')"
_FACT_TYPES = (
    "('preferred_language', 'budget_min', 'budget_max', 'currency', 'preferred_category', "
    "'preferred_color', 'preferred_material', 'dimension_requirement', 'location', "
    "'purchase_timeline', 'product_interest', 'objection', 'contact_time_preference', "
    "'seller_promise', 'customer_requested_follow_up')"
)
_FACT_STATUS = "('inferred', 'confirmed', 'rejected', 'expired', 'deleted')"


def upgrade() -> None:
    op.create_table(
        "reply_suggestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=True),
        sa.Column("model_code", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_milliseconds", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("cost_status", sa.String(length=32), nullable=False),
        sa.Column("estimated_cost_microunits", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("customer_state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("next_best_action_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("escalation_reason", sa.String(length=512), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("input_digest", postgresql.BYTEA(), nullable=True),
        sa.Column("output_digest", postgresql.BYTEA(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f("fk_reply_suggestion_runs_tenant_thread"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reply_suggestion_runs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_reply_suggestion_runs_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name=op.f("uq_reply_suggestion_runs_tenant_idem")
        ),
        sa.CheckConstraint(f"status IN {_RUN}", name=op.f("ck_reply_suggestion_runs_status")),
        sa.CheckConstraint(
            f"cost_status IN {_COST}", name=op.f("ck_reply_suggestion_runs_cost_status")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_reply_suggestion_runs_version_positive")),
        sa.CheckConstraint(
            "(cost_status <> 'known') OR (estimated_cost_microunits IS NOT NULL)",
            name=op.f("ck_reply_suggestion_runs_known_cost_requires_amount"),
        ),
        sa.CheckConstraint(
            "(cost_status <> 'unknown') OR (estimated_cost_microunits IS NULL)",
            name=op.f("ck_reply_suggestion_runs_unknown_cost_null_amount"),
        ),
    )
    op.create_index(
        op.f("ix_reply_suggestion_runs_tenant_thread_created"),
        "reply_suggestion_runs",
        ["tenant_id", "conversation_thread_id", "created_at"],
    )

    op.create_table(
        "reply_suggestion_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_key", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("objective", sa.String(length=128), nullable=False),
        sa.Column("confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("evidence_message_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("product_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "knowledge_citation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_recommended", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["reply_suggestion_runs.tenant_id", "reply_suggestion_runs.id"],
            name=op.f("fk_reply_suggestion_candidates_tenant_run"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reply_suggestion_candidates")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_reply_suggestion_candidates_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "candidate_key",
            name=op.f("uq_reply_suggestion_candidates_tenant_run_key"),
        ),
        sa.CheckConstraint(
            f"candidate_key IN {_KEYS}",
            name=op.f("ck_reply_suggestion_candidates_candidate_key"),
        ),
        sa.CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name=op.f("ck_reply_suggestion_candidates_confidence_range"),
        ),
    )
    op.create_index(
        op.f("ix_reply_suggestion_candidates_tenant_run"),
        "reply_suggestion_candidates",
        ["tenant_id", "run_id"],
    )

    op.create_table(
        "reply_suggestion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outbound_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["reply_suggestion_runs.tenant_id", "reply_suggestion_runs.id"],
            name=op.f("fk_reply_suggestion_events_tenant_run"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reply_suggestion_events")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_reply_suggestion_events_tenant_id_id")
        ),
        sa.CheckConstraint(
            f"event_type IN {_EVENTS}", name=op.f("ck_reply_suggestion_events_event_type")
        ),
    )
    op.create_index(
        op.f("ix_reply_suggestion_events_tenant_run"),
        "reply_suggestion_events",
        ["tenant_id", "run_id", "occurred_at"],
    )

    op.create_table(
        "buyer_memory_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column("display_value", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence_basis_points", sa.Integer(), nullable=False),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supersedes_fact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
            name=op.f("fk_buyer_memory_facts_tenant_thread"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buyer_memory_facts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_buyer_memory_facts_tenant_id_id")),
        sa.CheckConstraint(
            f"fact_type IN {_FACT_TYPES}", name=op.f("ck_buyer_memory_facts_fact_type")
        ),
        sa.CheckConstraint(f"status IN {_FACT_STATUS}", name=op.f("ck_buyer_memory_facts_status")),
        sa.CheckConstraint(
            "confidence_basis_points >= 0 AND confidence_basis_points <= 10000",
            name=op.f("ck_buyer_memory_facts_confidence_range"),
        ),
        sa.CheckConstraint(
            "(status <> 'confirmed') OR (source_message_id IS NOT NULL)",
            name=op.f("ck_buyer_memory_facts_confirmed_requires_source"),
        ),
        sa.CheckConstraint(
            "(status <> 'inferred') OR (expires_at IS NOT NULL)",
            name=op.f("ck_buyer_memory_facts_inferred_requires_expiry"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_buyer_memory_facts_version_positive")),
    )
    op.create_index(
        op.f("ix_buyer_memory_facts_tenant_thread_type"),
        "buyer_memory_facts",
        ["tenant_id", "conversation_thread_id", "fact_type"],
    )
    op.create_index(
        op.f("ix_buyer_memory_facts_tenant_lead"),
        "buyer_memory_facts",
        ["tenant_id", "lead_id"],
    )


def downgrade() -> None:
    op.drop_table("buyer_memory_facts")
    op.drop_table("reply_suggestion_events")
    op.drop_table("reply_suggestion_candidates")
    op.drop_table("reply_suggestion_runs")
