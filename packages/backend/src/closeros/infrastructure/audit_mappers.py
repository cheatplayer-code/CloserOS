"""ORM ↔ domain mapping for audit events."""

from __future__ import annotations

from closeros.domain.audit import (
    AuditAction,
    AuditActor,
    AuditActorType,
    AuditEvent,
    AuditMetadata,
    AuditScope,
    AuditTarget,
    AuditTargetType,
    MetadataScalar,
)
from closeros.infrastructure.audit_orm import AuditEventRow


def audit_event_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        scope=event.scope.value,
        tenant_id=event.tenant_id,
        actor_type=event.actor.actor_type.value,
        actor_id=event.actor.actor_id,
        action=event.action.value,
        target_type=event.target.target_type.value,
        target_id=event.target.target_id,
        occurred_at=event.occurred_at,
        correlation_id=event.correlation_id,
        event_metadata=event.metadata.to_mapping(),
    )


def audit_event_from_row(row: AuditEventRow) -> AuditEvent:
    metadata_mapping = row.event_metadata
    if not isinstance(metadata_mapping, dict):
        raise TypeError("metadata must be a dict")

    normalized_metadata: dict[str, MetadataScalar] = {}
    for key, value in metadata_mapping.items():
        if not isinstance(key, str):
            raise TypeError("metadata keys must be strings")
        if isinstance(value, (bool, int, str)):
            normalized_metadata[key] = value
        else:
            raise TypeError("metadata values must be safe scalar types")

    return AuditEvent(
        id=row.id,
        scope=AuditScope(row.scope),
        tenant_id=row.tenant_id,
        actor=AuditActor(
            actor_type=AuditActorType(row.actor_type),
            actor_id=row.actor_id,
        ),
        action=AuditAction(row.action),
        target=AuditTarget(
            target_type=AuditTargetType(row.target_type),
            target_id=row.target_id,
        ),
        occurred_at=row.occurred_at,
        correlation_id=row.correlation_id,
        metadata=AuditMetadata.from_mapping(normalized_metadata),
    )
