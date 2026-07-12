"""Safe audit event builders for NOPQ AI gateway and analysis actions."""

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


def analysis_requested_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    provider_code: str,
    purpose_code: str,
    prompt_version: str,
    rubric_version: str,
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
        action=AuditAction.ANALYSIS_REQUESTED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            provider_code=provider_code,
            purpose_code=purpose_code,
            policy_version=prompt_version,
            rubric_version=rubric_version,
        ),
    )


def analysis_completed_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    issue_count: int,
    citation_count: int,
    token_count: int,
    latency_bucket: str,
    provider_code: str,
    purpose_code: str,
    rubric_version: str,
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
        action=AuditAction.ANALYSIS_COMPLETED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            issue_count=issue_count,
            citation_count=citation_count,
            token_count=token_count,
            latency_bucket=latency_bucket,
            provider_code=provider_code,
            purpose_code=purpose_code,
            rubric_version=rubric_version,
            budget_status="within_budget",
        ),
    )


def analysis_blocked_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    reason_code: str,
    budget_status: str,
    provider_code: str,
    purpose_code: str,
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
        action=AuditAction.ANALYSIS_BLOCKED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            reason_code=reason_code,
            budget_status=budget_status,
            provider_code=provider_code,
            purpose_code=purpose_code,
        ),
    )


def analysis_failed_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    reason_code: str,
    error_class: str,
    provider_code: str,
    purpose_code: str,
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
        action=AuditAction.ANALYSIS_FAILED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            reason_code=reason_code,
            error_class=error_class,
            provider_code=provider_code,
            purpose_code=purpose_code,
        ),
    )


def ai_budget_exceeded_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    provider_code: str,
    purpose_code: str,
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
        action=AuditAction.AI_BUDGET_EXCEEDED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            reason_code="daily_budget_exceeded",
            budget_status="exceeded",
            provider_code=provider_code,
            purpose_code=purpose_code,
        ),
    )
