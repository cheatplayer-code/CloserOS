"""SQLAlchemy ORM model for immutable audit events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditScope,
    AuditTargetType,
)
from closeros.infrastructure.authentication_orm import Base

_ACTION_VALUES = tuple(action.value for action in AuditAction)
_ACTOR_TYPE_VALUES = tuple(actor_type.value for actor_type in AuditActorType)
_SCOPE_VALUES = tuple(scope.value for scope in AuditScope)
_TARGET_TYPE_VALUES = tuple(target_type.value for target_type in AuditTargetType)


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            f"scope IN ({_quoted_values(_SCOPE_VALUES)})",
            name="scope",
        ),
        CheckConstraint(
            f"actor_type IN ({_quoted_values(_ACTOR_TYPE_VALUES)})",
            name="actor_type",
        ),
        CheckConstraint(
            f"action IN ({_quoted_values(_ACTION_VALUES)})",
            name="action",
        ),
        CheckConstraint(
            f"target_type IN ({_quoted_values(_TARGET_TYPE_VALUES)})",
            name="target_type",
        ),
        CheckConstraint(
            "(scope = 'tenant' AND tenant_id IS NOT NULL) OR "
            "(scope = 'global' AND tenant_id IS NULL)",
            name="scope_tenant",
        ),
        CheckConstraint(
            "(actor_type = 'anonymous' AND actor_id IS NULL) OR "
            "(actor_type = 'user' AND actor_id IS NOT NULL) OR "
            "(actor_type = 'system' AND actor_id IS NULL) OR "
            "(actor_type = 'service' AND actor_id IS NOT NULL)",
            name="actor_identity",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="metadata_object",
        ),
        Index("ix_audit_events_tenant_id_occurred_at_id", "tenant_id", "occurred_at", "id"),
        Index("ix_audit_events_action_occurred_at", "action", "occurred_at"),
        Index("ix_audit_events_actor_id_occurred_at", "actor_id", "occurred_at"),
        Index("ix_audit_events_target_type_target_id", "target_type", "target_id"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
    )
