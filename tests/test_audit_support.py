"""Shared synthetic helpers for audit subsystem tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditEvent,
    AuditScope,
    AuditTargetType,
    build_audit_event,
)

NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000999")
USER_ID = UUID("00000000-0000-0000-0000-000000000020")
DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")


def append_event(
    *,
    scope: AuditScope = AuditScope.TENANT,
    tenant_id: UUID | None = DEFAULT_TENANT_ID,
    actor_type: AuditActorType = AuditActorType.USER,
    actor_id: UUID | None = USER_ID,
    action: AuditAction = AuditAction.AUDIT_LOG_VIEWED,
    target_type: AuditTargetType = AuditTargetType.AUDIT_LOG,
    target_id: UUID | None = DEFAULT_TENANT_ID,
    occurred_at: datetime = NOW,
    correlation_id: UUID = CORRELATION_ID,
    event_id: UUID | None = None,
    metadata: dict[str, str | int | bool] | None = None,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id or uuid4(),
        scope=scope,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        metadata=metadata or {"outcome": "success"},
    )


def tenant_event(
    *,
    tenant_id: UUID,
    action: AuditAction = AuditAction.AUDIT_LOG_VIEWED,
    occurred_at: datetime = NOW,
    event_id: UUID | None = None,
    correlation_id: UUID = CORRELATION_ID,
) -> AuditEvent:
    return append_event(
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=AuditActorType.USER,
        actor_id=USER_ID,
        action=action,
        target_type=AuditTargetType.AUDIT_LOG,
        target_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        correlation_id=correlation_id,
    )
