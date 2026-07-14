"""Safe audit builders for product catalog mutations and AI fact usage."""

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


def _metadata(**values: MetadataScalar) -> dict[str, MetadataScalar]:
    return {"outcome": "success", **values}


def catalog_product_mutated_event(
    *,
    tenant_id: UUID,
    product_id: UUID,
    action: AuditAction,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    status: str,
    category_code: str | None = None,
) -> AuditEvent:
    meta: dict[str, MetadataScalar] = _metadata(status=status)
    if category_code is not None:
        meta["category_code"] = category_code
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=AuditTargetType.CATALOG_PRODUCT,
        target_id=product_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=meta,
    )


def catalog_import_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    action: AuditAction,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    status: str,
    affected_count: int | None = None,
) -> AuditEvent:
    meta: dict[str, MetadataScalar] = _metadata(status=status)
    if affected_count is not None:
        meta["affected_count"] = affected_count
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=AuditTargetType.CATALOG_IMPORT_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=meta,
    )


def catalog_fact_queried_event(
    *,
    tenant_id: UUID,
    product_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    purpose_code: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.CATALOG_FACT_QUERIED,
        target_type=AuditTargetType.CATALOG_PRODUCT,
        target_id=product_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(purpose_code=purpose_code),
    )
