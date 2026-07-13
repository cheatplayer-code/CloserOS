"""Mappers for XY production operations ORM rows."""

from __future__ import annotations

from closeros.application.notification_ports import NotificationDeliveryAttemptRecord
from closeros.domain.legal_hold import LegalHold, LegalHoldStatus
from closeros.domain.notification import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationKind,
)
from closeros.domain.retention_execution import (
    RetentionPurgeBatch,
    RetentionPurgeBatchStatus,
    RetentionPurgeRun,
    RetentionPurgeRunStatus,
)
from closeros.infrastructure.xy_orm import (
    LegalHoldRow,
    NotificationDeliveryAttemptRow,
    NotificationDeliveryRow,
    RetentionPurgeBatchRow,
    RetentionPurgeRunRow,
)


def notification_delivery_to_row(delivery: NotificationDelivery) -> NotificationDeliveryRow:
    return NotificationDeliveryRow(
        id=delivery.id,
        tenant_id=delivery.tenant_id,
        payload_tenant_id=delivery.payload_tenant_id,
        kind=delivery.kind.value,
        status=delivery.status.value,
        template_code=delivery.template_code,
        template_version=delivery.template_version,
        recipient_hash=delivery.recipient_hash,
        encrypted_payload_content_id=delivery.encrypted_payload_content_id,
        idempotency_key=delivery.idempotency_key,
        attempt_count=delivery.attempt_count,
        correlation_id=delivery.correlation_id,
        delivered_at=delivery.delivered_at,
        last_error_code=delivery.last_error_code,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


def notification_delivery_row_to_domain(row: NotificationDeliveryRow) -> NotificationDelivery:
    return NotificationDelivery(
        id=row.id,
        tenant_id=row.tenant_id,
        payload_tenant_id=row.payload_tenant_id,
        kind=NotificationKind(row.kind),
        status=NotificationDeliveryStatus(row.status),
        template_code=row.template_code,
        template_version=row.template_version,
        recipient_hash=row.recipient_hash,
        encrypted_payload_content_id=row.encrypted_payload_content_id,
        idempotency_key=row.idempotency_key,
        attempt_count=row.attempt_count,
        correlation_id=row.correlation_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        delivered_at=row.delivered_at,
        last_error_code=row.last_error_code,
    )


def notification_attempt_to_row(
    attempt: NotificationDeliveryAttemptRecord,
) -> NotificationDeliveryAttemptRow:
    return NotificationDeliveryAttemptRow(
        id=attempt.id,
        tenant_id=attempt.tenant_id,
        delivery_id=attempt.delivery_id,
        attempt_number=attempt.attempt_number,
        outcome=attempt.outcome.value,
        error_code=attempt.error_code,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
    )


def legal_hold_to_row(legal_hold: LegalHold) -> LegalHoldRow:
    return LegalHoldRow(
        id=legal_hold.id,
        tenant_id=legal_hold.tenant_id,
        status=legal_hold.status.value,
        reason_code=legal_hold.reason_code,
        reason_detail=legal_hold.reason_detail,
        created_by_user_id=legal_hold.created_by_user_id,
        released_by_user_id=legal_hold.released_by_user_id,
        created_at=legal_hold.created_at,
        released_at=legal_hold.released_at,
        updated_at=legal_hold.updated_at,
    )


def legal_hold_row_to_domain(row: LegalHoldRow) -> LegalHold:
    return LegalHold(
        id=row.id,
        tenant_id=row.tenant_id,
        status=LegalHoldStatus(row.status),
        reason_code=row.reason_code,
        reason_detail=row.reason_detail,
        created_by_user_id=row.created_by_user_id,
        released_by_user_id=row.released_by_user_id,
        created_at=row.created_at,
        released_at=row.released_at,
        updated_at=row.updated_at,
    )


def retention_purge_run_to_row(purge_run: RetentionPurgeRun) -> RetentionPurgeRunRow:
    return RetentionPurgeRunRow(
        id=purge_run.id,
        tenant_id=purge_run.tenant_id,
        status=purge_run.status.value,
        dry_run=purge_run.dry_run,
        expires_before=purge_run.expires_before,
        items_scanned=purge_run.items_scanned,
        items_deleted=purge_run.items_deleted,
        items_skipped_legal_hold=purge_run.items_skipped_legal_hold,
        started_at=purge_run.started_at,
        completed_at=purge_run.completed_at,
        last_error_code=purge_run.last_error_code,
        claim_token=purge_run.claim_token,
        claim_expires_at=purge_run.claim_expires_at,
        version=purge_run.version,
        created_at=purge_run.created_at,
        updated_at=purge_run.updated_at,
    )


def retention_purge_run_row_to_domain(row: RetentionPurgeRunRow) -> RetentionPurgeRun:
    return RetentionPurgeRun(
        id=row.id,
        tenant_id=row.tenant_id,
        status=RetentionPurgeRunStatus(row.status),
        dry_run=row.dry_run,
        expires_before=row.expires_before,
        items_scanned=row.items_scanned,
        items_deleted=row.items_deleted,
        items_skipped_legal_hold=row.items_skipped_legal_hold,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_error_code=row.last_error_code,
        claim_token=row.claim_token,
        claim_expires_at=row.claim_expires_at,
        version=row.version,
    )


def retention_purge_batch_to_row(batch: RetentionPurgeBatch) -> RetentionPurgeBatchRow:
    return RetentionPurgeBatchRow(
        id=batch.id,
        tenant_id=batch.tenant_id,
        purge_run_id=batch.purge_run_id,
        deleted_content_id=batch.deleted_content_id,
        status=batch.status.value,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
    )


def retention_purge_batch_row_to_domain(row: RetentionPurgeBatchRow) -> RetentionPurgeBatch:
    return RetentionPurgeBatch(
        id=row.id,
        tenant_id=row.tenant_id,
        purge_run_id=row.purge_run_id,
        deleted_content_id=row.deleted_content_id,
        status=RetentionPurgeBatchStatus(row.status),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
