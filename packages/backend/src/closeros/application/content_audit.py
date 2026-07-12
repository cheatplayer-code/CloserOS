"""Safe audit event builders for encrypted-content actions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.domain.audit import (
    AuditAction,
    AuditActor,
    AuditActorType,
    AuditEvent,
    AuditScope,
    AuditTargetType,
    MetadataScalar,
    build_audit_event,
)
from closeros.domain.encrypted_content import ContentAccessPurpose, EncryptedContentKind
from closeros.domain.outbox import OutboxJobKind


def _tenant_metadata(**values: MetadataScalar) -> dict[str, MetadataScalar]:
    return {"outcome": "success", **values}


def content_encrypted_stored_event(
    *,
    tenant_id: UUID,
    content_id: UUID,
    kind: EncryptedContentKind,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_STORED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=kind.value,
            key_version_code=key_version,
        ),
    )


def content_encrypted_accessed_event(
    *,
    tenant_id: UUID,
    content_id: UUID,
    kind: EncryptedContentKind,
    purpose: ContentAccessPurpose,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_ACCESSED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=kind.value,
            key_version_code=key_version,
            reason_code=purpose.value,
        ),
    )


def content_key_rewrapped_event(
    *,
    tenant_id: UUID,
    content_id: UUID,
    kind: EncryptedContentKind,
    previous_key_version: str,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_KEY_REWRAPPED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=kind.value,
            key_version_code=key_version,
            previous_status=previous_key_version,
            new_status=key_version,
        ),
    )


def raw_message_stored_event(
    *,
    tenant_id: UUID,
    message_id: UUID,
    content_id: UUID,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_STORED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=EncryptedContentKind.RAW_MESSAGE.value,
            key_version_code=key_version,
            affected_count=1,
        ),
    )


def message_edit_stored_event(
    *,
    tenant_id: UUID,
    edit_event_id: UUID,
    message_id: UUID,
    content_id: UUID,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_STORED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=EncryptedContentKind.RAW_MESSAGE.value,
            key_version_code=key_version,
            reason_code="message_edit",
        ),
    )


def provider_payload_attached_event(
    *,
    tenant_id: UUID,
    webhook_event_id: UUID,
    content_id: UUID,
    key_version: str,
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
        action=AuditAction.ENCRYPTED_CONTENT_STORED,
        target_type=AuditTargetType.ENCRYPTED_CONTENT,
        target_id=content_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            content_kind=EncryptedContentKind.PROVIDER_PAYLOAD.value,
            key_version_code=key_version,
            job_kind=OutboxJobKind.WEBHOOK_NORMALIZE.value,
        ),
    )


def system_service_actor(*, service_id: UUID) -> AuditActor:
    return AuditActor(actor_type=AuditActorType.SERVICE, actor_id=service_id)
