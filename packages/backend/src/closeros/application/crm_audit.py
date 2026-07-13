"""Audit event builders for CRM operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditEvent,
    AuditScope,
    AuditTargetType,
    MetadataScalar,
    build_audit_event,
)


def crm_connection_event(
    *,
    action: AuditAction,
    tenant_id: UUID,
    connection_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    outcome: str | None = None,
) -> AuditEvent:
    metadata: dict[str, MetadataScalar] | None = (
        {"outcome": outcome} if outcome is not None else None
    )
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=AuditTargetType.CRM_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=metadata,
    )


__all__ = ["crm_connection_event"]
