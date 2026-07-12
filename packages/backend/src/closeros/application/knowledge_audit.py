"""Safe audit builders for knowledge lifecycle and retrieval actions."""

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


def knowledge_document_uploaded_event(
    *,
    tenant_id: UUID,
    document_id: UUID,
    source_type: str,
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
        action=AuditAction.KNOWLEDGE_DOCUMENT_UPLOADED,
        target_type=AuditTargetType.KNOWLEDGE_DOCUMENT,
        target_id=document_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(source_type=source_type),
    )


def knowledge_version_approved_event(
    *,
    tenant_id: UUID,
    version_id: UUID,
    version_number: int,
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
        action=AuditAction.KNOWLEDGE_VERSION_APPROVED,
        target_type=AuditTargetType.KNOWLEDGE_DOCUMENT_VERSION,
        target_id=version_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(version_number=version_number),
    )


def knowledge_version_indexed_event(
    *,
    tenant_id: UUID,
    version_id: UUID,
    version_number: int,
    chunk_count: int,
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
        action=AuditAction.KNOWLEDGE_VERSION_INDEXED,
        target_type=AuditTargetType.KNOWLEDGE_DOCUMENT_VERSION,
        target_id=version_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(version_number=version_number, affected_count=chunk_count),
    )


def knowledge_version_revoked_event(
    *,
    tenant_id: UUID,
    version_id: UUID,
    version_number: int,
    revoked_chunk_count: int,
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
        action=AuditAction.KNOWLEDGE_VERSION_REVOKED,
        target_type=AuditTargetType.KNOWLEDGE_DOCUMENT_VERSION,
        target_id=version_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(version_number=version_number, affected_count=revoked_chunk_count),
    )


def knowledge_retrieval_completed_event(
    *,
    tenant_id: UUID,
    analysis_target_id: UUID,
    purpose_code: str,
    chunk_count: int,
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
        action=AuditAction.KNOWLEDGE_RETRIEVAL_COMPLETED,
        target_type=AuditTargetType.CONVERSATION_ANALYSIS_RUN,
        target_id=analysis_target_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_metadata(purpose_code=purpose_code, affected_count=chunk_count),
    )
