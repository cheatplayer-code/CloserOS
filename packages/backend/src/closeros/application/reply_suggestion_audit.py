"""Safe audit builders for reply suggestion and buyer memory actions."""

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


def reply_suggestion_requested_event(
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
        action=AuditAction.REPLY_SUGGESTION_REQUESTED,
        target_type=AuditTargetType.REPLY_SUGGESTION_RUN,
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


def reply_suggestion_completed_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    candidate_count: int,
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
        action=AuditAction.REPLY_SUGGESTION_COMPLETED,
        target_type=AuditTargetType.REPLY_SUGGESTION_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            affected_count=candidate_count,
            token_count=token_count,
            latency_bucket=latency_bucket,
            provider_code=provider_code,
            purpose_code=purpose_code,
            rubric_version=rubric_version,
            budget_status="unknown",
        ),
    )


def reply_suggestion_blocked_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    reason_code: str,
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
        action=AuditAction.REPLY_SUGGESTION_BLOCKED,
        target_type=AuditTargetType.REPLY_SUGGESTION_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            reason_code=reason_code,
            provider_code=provider_code,
            purpose_code=purpose_code,
            budget_status="not_applicable",
        ),
    )


def reply_suggestion_selected_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
    candidate_key: str,
    edit_basis_points: int,
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
        action=AuditAction.REPLY_SUGGESTION_SELECTED,
        target_type=AuditTargetType.REPLY_SUGGESTION_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(
            candidate_key=candidate_key,
            edit_basis_points=edit_basis_points,
        ),
    )


def reply_suggestion_rejected_event(
    *,
    tenant_id: UUID,
    run_id: UUID,
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
        action=AuditAction.REPLY_SUGGESTION_REJECTED,
        target_type=AuditTargetType.REPLY_SUGGESTION_RUN,
        target_id=run_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(),
    )


def buyer_memory_confirmed_event(
    *,
    tenant_id: UUID,
    fact_id: UUID,
    fact_type: str,
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
        action=AuditAction.BUYER_MEMORY_CONFIRMED,
        target_type=AuditTargetType.BUYER_MEMORY_FACT,
        target_id=fact_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(fact_type=fact_type),
    )


def buyer_memory_corrected_event(
    *,
    tenant_id: UUID,
    fact_id: UUID,
    fact_type: str,
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
        action=AuditAction.BUYER_MEMORY_CORRECTED,
        target_type=AuditTargetType.BUYER_MEMORY_FACT,
        target_id=fact_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(fact_type=fact_type),
    )


def buyer_memory_deleted_event(
    *,
    tenant_id: UUID,
    fact_id: UUID,
    fact_type: str,
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
        action=AuditAction.BUYER_MEMORY_DELETED,
        target_type=AuditTargetType.BUYER_MEMORY_FACT,
        target_id=fact_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(fact_type=fact_type),
    )
