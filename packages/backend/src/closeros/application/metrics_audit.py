"""Safe audit event builders for metrics actions."""

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


def _tenant_metadata(**values: MetadataScalar) -> dict[str, MetadataScalar]:
    return {"outcome": "success", **values}


def metrics_recalculation_requested_event(
    *,
    tenant_id: UUID,
    outbox_job_id: UUID,
    formula_version: str,
    window_code: str,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.METRICS_RECALCULATION_REQUESTED,
        target_type=AuditTargetType.OUTBOX_JOB,
        target_id=outbox_job_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            formula_version=formula_version,
            window_code=window_code,
            job_kind="metrics.recalculate",
        ),
    )


def metrics_snapshot_completed_event(
    *,
    tenant_id: UUID,
    snapshot_id: UUID,
    metric_scope: str,
    formula_version: str,
    window_code: str,
    affected_count: int,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.METRICS_SNAPSHOT_COMPLETED,
        target_type=AuditTargetType.METRIC_SNAPSHOT,
        target_id=snapshot_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            metric_scope=metric_scope,
            formula_version=formula_version,
            window_code=window_code,
            affected_count=affected_count,
        ),
    )


def metrics_viewed_event(
    *,
    tenant_id: UUID,
    metric_scope: str,
    formula_version: str,
    window_code: str,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID,
    event_id: UUID,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.METRICS_VIEWED,
        target_type=AuditTargetType.TENANT,
        target_id=tenant_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            metric_scope=metric_scope,
            formula_version=formula_version,
            window_code=window_code,
        ),
    )
