"""Safe audit event builders for privacy redaction actions."""

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


def content_sanitization_completed_event(
    *,
    tenant_id: UUID,
    sanitization_id: UUID,
    finding_count: int,
    critical_finding_count: int,
    eligibility_code: str,
    policy_version: str,
    detector_version: str,
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
        action=AuditAction.CONTENT_SANITIZATION_COMPLETED,
        target_type=AuditTargetType.CONTENT_SANITIZATION,
        target_id=sanitization_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            finding_count=finding_count,
            critical_finding_count=critical_finding_count,
            eligibility_code=eligibility_code,
            policy_version=policy_version,
            detector_version=detector_version,
            sanitization_status="completed",
        ),
    )


def content_sanitization_blocked_event(
    *,
    tenant_id: UUID,
    sanitization_id: UUID,
    finding_count: int,
    critical_finding_count: int,
    eligibility_code: str,
    policy_version: str,
    reason_code: str,
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
        action=AuditAction.CONTENT_SANITIZATION_BLOCKED,
        target_type=AuditTargetType.CONTENT_SANITIZATION,
        target_id=sanitization_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            finding_count=finding_count,
            critical_finding_count=critical_finding_count,
            eligibility_code=eligibility_code,
            policy_version=policy_version,
            reason_code=reason_code,
            sanitization_status="completed",
        ),
    )
