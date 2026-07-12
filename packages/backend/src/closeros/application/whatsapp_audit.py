"""Safe audit event builders for WhatsApp provider actions."""

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


def whatsapp_connection_created_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
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
        action=AuditAction.WHATSAPP_CONNECTION_CREATED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="draft"),
    )


def whatsapp_connection_verified_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
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
        action=AuditAction.WHATSAPP_CONNECTION_VERIFIED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", outcome=outcome),
    )


def whatsapp_connection_disabled_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
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
        action=AuditAction.WHATSAPP_CONNECTION_DISABLED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="disabled"),
    )


def webhook_rejected_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    reason_code: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.WEBHOOK_REJECTED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", reason_code=reason_code),
    )


def media_quarantined_event(
    *,
    tenant_id: UUID,
    media_reference_id: UUID,
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
        action=AuditAction.MEDIA_QUARANTINED,
        target_type=AuditTargetType.PROVIDER_MEDIA_REFERENCE,
        target_id=media_reference_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code="whatsapp_cloud",
            status="quarantined_pending_scan",
        ),
    )


def provider_templates_sync_completed_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    operation_count: int,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.PROVIDER_TEMPLATES_SYNC_COMPLETED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code="whatsapp_cloud",
            operation_count=operation_count,
        ),
    )


def provider_templates_sync_failed_event(
    *,
    tenant_id: UUID,
    connection_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    reason_code: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.PROVIDER_TEMPLATES_SYNC_FAILED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=connection_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", reason_code=reason_code),
    )


def outbound_draft_created_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    outbound_kind: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.OUTBOUND_DRAFT_CREATED,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", outcome=outbound_kind),
    )


def outbound_message_approved_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
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
        action=AuditAction.OUTBOUND_MESSAGE_APPROVED,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="approved"),
    )


def outbound_message_queued_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
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
        action=AuditAction.OUTBOUND_MESSAGE_QUEUED,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="queued"),
    )


def outbound_provider_accepted_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
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
        action=AuditAction.OUTBOUND_PROVIDER_ACCEPTED,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="provider_accepted"),
    )


def outbound_delivery_unknown_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
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
        action=AuditAction.OUTBOUND_DELIVERY_UNKNOWN,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", status="delivery_unknown"),
    )


def outbound_delivery_failed_event(
    *,
    tenant_id: UUID,
    outbound_message_id: UUID,
    occurred_at: datetime,
    audit_context: AuditContext,
    actor_type: AuditActorType,
    actor_id: UUID | None,
    event_id: UUID,
    reason_code: str,
) -> AuditEvent:
    return build_audit_event(
        event_id=event_id,
        scope=AuditScope.TENANT,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.OUTBOUND_DELIVERY_FAILED,
        target_type=AuditTargetType.OUTBOUND_MESSAGE,
        target_id=outbound_message_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code="whatsapp_cloud", reason_code=reason_code),
    )


def whatsapp_reconciliation_completed_event(
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
        action=AuditAction.WHATSAPP_RECONCILIATION_COMPLETED,
        target_type=AuditTargetType.WHATSAPP_CLOUD_CONNECTION,
        target_id=None,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code="whatsapp_cloud",
            affected_count=affected_count,
        ),
    )
