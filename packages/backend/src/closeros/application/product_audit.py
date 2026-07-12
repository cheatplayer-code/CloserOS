"""Safe audit event builders for RSTU product workspace actions."""

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
    build_audit_event,
)


def follow_up_task_created_event(
    *,
    tenant_id: UUID,
    task_id: UUID,
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
        action=AuditAction.FOLLOW_UP_TASK_CREATED,
        target_type=AuditTargetType.FOLLOW_UP_TASK,
        target_id=task_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "created"},
    )


def follow_up_task_mutated_event(
    *,
    action: AuditAction,
    tenant_id: UUID,
    task_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    outcome: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=AuditTargetType.FOLLOW_UP_TASK,
        target_id=task_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": outcome},
    )


def follow_up_task_viewed_event(
    *,
    tenant_id: UUID,
    task_id: UUID,
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
        action=AuditAction.FOLLOW_UP_TASK_VIEWED,
        target_type=AuditTargetType.FOLLOW_UP_TASK,
        target_id=task_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "viewed"},
    )


def conversation_list_viewed_event(
    *,
    tenant_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    affected_count: int,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.CONVERSATION_LIST_VIEWED,
        target_type=AuditTargetType.CONVERSATION_THREAD,
        target_id=tenant_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "viewed", "affected_count": affected_count},
    )


def conversation_detail_viewed_event(
    *,
    tenant_id: UUID,
    conversation_thread_id: UUID,
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
        action=AuditAction.CONVERSATION_DETAIL_VIEWED,
        target_type=AuditTargetType.CONVERSATION_THREAD,
        target_id=conversation_thread_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "viewed"},
    )


def dashboard_viewed_event(
    *,
    tenant_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    window_code: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.DASHBOARD_VIEWED,
        target_type=AuditTargetType.DASHBOARD,
        target_id=tenant_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "viewed", "window_code": window_code},
    )


def scorecard_viewed_event(
    *,
    tenant_id: UUID,
    membership_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    score_formula_version: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.SCORECARD_VIEWED,
        target_type=AuditTargetType.SCORECARD,
        target_id=membership_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata={"outcome": "viewed", "score_formula_version": score_formula_version},
    )
