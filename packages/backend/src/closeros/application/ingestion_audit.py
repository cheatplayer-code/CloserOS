"""Safe audit event builders for ingestion and CSV import actions."""

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
from closeros.domain.canonical_enums import ProviderKind, WebhookProcessingStatus
from closeros.domain.csv_import import CsvImportStatus


def _tenant_metadata(**values: MetadataScalar) -> dict[str, MetadataScalar]:
    return {"outcome": "success", **values}


def webhook_accepted_event(
    *,
    tenant_id: UUID,
    webhook_event_id: UUID,
    provider_code: str,
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
        action=AuditAction.WEBHOOK_ACCEPTED,
        target_type=AuditTargetType.WEBHOOK_EVENT,
        target_id=webhook_event_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code=provider_code, status=WebhookProcessingStatus.ACKNOWLEDGED.value
        ),
    )


def webhook_duplicate_accepted_event(
    *,
    tenant_id: UUID,
    webhook_event_id: UUID,
    provider_code: str,
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
        action=AuditAction.WEBHOOK_DUPLICATE_ACCEPTED,
        target_type=AuditTargetType.WEBHOOK_EVENT,
        target_id=webhook_event_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(provider_code=provider_code, outcome_code="duplicate"),
    )


def webhook_normalized_event(
    *,
    tenant_id: UUID,
    webhook_event_id: UUID,
    provider_code: str,
    operation_count: int,
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
        action=AuditAction.WEBHOOK_NORMALIZED,
        target_type=AuditTargetType.WEBHOOK_EVENT,
        target_id=webhook_event_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code=provider_code,
            operation_count=operation_count,
            status=WebhookProcessingStatus.PROCESSED.value,
        ),
    )


def webhook_normalization_failed_event(
    *,
    tenant_id: UUID,
    webhook_event_id: UUID,
    provider_code: str,
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
        action=AuditAction.WEBHOOK_NORMALIZATION_FAILED,
        target_type=AuditTargetType.WEBHOOK_EVENT,
        target_id=webhook_event_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            provider_code=provider_code,
            reason_code=reason_code,
            outcome_code="failed",
        ),
    )


def csv_import_uploaded_event(
    *,
    tenant_id: UUID,
    import_id: UUID,
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
        action=AuditAction.CSV_IMPORT_UPLOADED,
        target_type=AuditTargetType.CSV_IMPORT_BATCH,
        target_id=import_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(source_type="csv", status=CsvImportStatus.UPLOADED.value),
    )


def csv_import_started_event(
    *,
    tenant_id: UUID,
    import_id: UUID,
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
        action=AuditAction.CSV_IMPORT_STARTED,
        target_type=AuditTargetType.CSV_IMPORT_BATCH,
        target_id=import_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(source_type="csv", status=CsvImportStatus.READY.value),
    )


def csv_import_completed_event(
    *,
    tenant_id: UUID,
    import_id: UUID,
    status: CsvImportStatus,
    succeeded_count: int,
    failed_count: int,
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
        action=AuditAction.CSV_IMPORT_COMPLETED,
        target_type=AuditTargetType.CSV_IMPORT_BATCH,
        target_id=import_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(
            source_type="csv",
            status=status.value,
            affected_count=succeeded_count,
            operation_count=failed_count,
        ),
    )


def csv_import_cancelled_event(
    *,
    tenant_id: UUID,
    import_id: UUID,
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
        action=AuditAction.CSV_IMPORT_CANCELLED,
        target_type=AuditTargetType.CSV_IMPORT_BATCH,
        target_id=import_id,
        occurred_at=occurred_at,
        correlation_id=audit_context.correlation_id,
        metadata=_tenant_metadata(source_type="csv", status=CsvImportStatus.CANCELLED.value),
    )


def provider_code_for_kind(provider_kind: ProviderKind) -> str:
    return provider_kind.value
