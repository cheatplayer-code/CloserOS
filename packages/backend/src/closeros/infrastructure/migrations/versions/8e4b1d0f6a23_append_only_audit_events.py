"""Append-only audit_events schema with database-level immutability.

Revision ID: 8e4b1d0f6a23
Revises: 7f3a9c2e1b04
Create Date: 2026-07-12 10:30:00.000000

Creates ``audit_events`` with domain-aligned CHECK constraints, query indexes,
and a trigger that rejects UPDATE and DELETE. No foreign keys reference actors
or tenants so audit history survives entity deletion.

Controlled retention deletion must use a dedicated future mechanism and must not
grant ordinary mutation rights on this table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8e4b1d0f6a23"
down_revision: str | Sequence[str] | None = "7f3a9c2e1b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTION_VALUES = (
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

_ACTOR_TYPE_VALUES = ("anonymous", "user", "system", "service")
_SCOPE_VALUES = ("global", "tenant")
_TARGET_TYPE_VALUES = ("user", "credential", "session", "tenant", "audit_log", "authentication")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "recorded_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"scope IN ({_quoted(_SCOPE_VALUES)})",
            name=op.f("ck_audit_events_scope"),
        ),
        sa.CheckConstraint(
            f"actor_type IN ({_quoted(_ACTOR_TYPE_VALUES)})",
            name=op.f("ck_audit_events_actor_type"),
        ),
        sa.CheckConstraint(
            f"action IN ({_quoted(_ACTION_VALUES)})",
            name=op.f("ck_audit_events_action"),
        ),
        sa.CheckConstraint(
            f"target_type IN ({_quoted(_TARGET_TYPE_VALUES)})",
            name=op.f("ck_audit_events_target_type"),
        ),
        sa.CheckConstraint(
            "(scope = 'tenant' AND tenant_id IS NOT NULL) OR "
            "(scope = 'global' AND tenant_id IS NULL)",
            name=op.f("ck_audit_events_scope_tenant"),
        ),
        sa.CheckConstraint(
            "(actor_type = 'anonymous' AND actor_id IS NULL) OR "
            "(actor_type = 'user' AND actor_id IS NOT NULL) OR "
            "(actor_type = 'system' AND actor_id IS NULL) OR "
            "(actor_type = 'service' AND actor_id IS NOT NULL)",
            name=op.f("ck_audit_events_actor_identity"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_audit_events_metadata_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_tenant_id_occurred_at_id"),
        "audit_events",
        ["tenant_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_action_occurred_at"),
        "audit_events",
        ["action", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_actor_id_occurred_at"),
        "audit_events",
        ["actor_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_target_type_target_id"),
        "audit_events",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_correlation_id"),
        "audit_events",
        ["correlation_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events rows are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_update
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION audit_events_reject_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_reject_mutation()")
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_index(
        op.f("ix_audit_events_target_type_target_id"),
        table_name="audit_events",
    )
    op.drop_index(op.f("ix_audit_events_actor_id_occurred_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action_occurred_at"), table_name="audit_events")
    op.drop_index(
        op.f("ix_audit_events_tenant_id_occurred_at_id"),
        table_name="audit_events",
    )
    op.drop_table("audit_events")
