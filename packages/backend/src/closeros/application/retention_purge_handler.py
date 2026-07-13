"""Outbox handler for retention.delete jobs."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from closeros.application.encrypted_content_persistence import EncryptedContentRetentionFilter
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.encrypted_content import EncryptedContent
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)
from closeros.domain.retention_execution import (
    RetentionPurgeBatch,
    RetentionPurgeBatchStatus,
    RetentionPurgeRun,
    RetentionPurgeRunStatus,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_CLAIM_LEASE = timedelta(minutes=5)
_RENEW_AFTER_DELETIONS = 10


class RetentionPurgeHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("retention purge failed")


class RetentionPurgeHandler:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        legal_hold_service: LegalHoldService,
        batch_size: int = 100,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._legal_hold_service = legal_hold_service
        self._batch_size = batch_size

    async def handle(self, *, job: OutboxJob) -> None:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )
        reference = job.reference
        if reference.resource_type != "retention_purge_run":
            raise RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            )

        occurred_at = job.processing_started_at or job.created_at
        claim_token = job.claim_token or self._uuid_factory()

        if await self._legal_hold_service.tenant_has_active_hold(tenant_id=tenant_id):
            await self._mark_run_paused(
                tenant_id=tenant_id,
                purge_run_id=reference.resource_id,
                occurred_at=occurred_at,
                skipped=True,
            )
            return

        claimed = await self._claim_run(
            tenant_id=tenant_id,
            purge_run_id=reference.resource_id,
            claim_token=claim_token,
            occurred_at=occurred_at,
        )
        if claimed is None:
            raise RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.STALE_CLAIM,
                permanent=False,
            )
        if claimed.status in {
            RetentionPurgeRunStatus.COMPLETED,
            RetentionPurgeRunStatus.CANCELLED,
            RetentionPurgeRunStatus.PAUSED,
        }:
            return

        if await self._legal_hold_service.tenant_has_active_hold(tenant_id=tenant_id):
            await self._mark_run_paused(
                tenant_id=tenant_id,
                purge_run_id=claimed.id,
                occurred_at=occurred_at,
                skipped=True,
            )
            return

        uow = self._uow_factory()
        async with uow:
            due = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=tenant_id,
                    expires_before=claimed.expires_before,
                    limit=self._batch_size,
                )
            )

        batch_deleted = 0
        deletions_since_renewal = 0
        for content in due:
            claimed = await self._maybe_renew_claim(
                claimed=claimed,
                claim_token=claim_token,
                occurred_at=occurred_at,
                deletions_since_renewal=deletions_since_renewal,
            )
            deletions_since_renewal = 0

            paused = await self._delete_content_under_lock(
                tenant_id=tenant_id,
                purge_run_id=claimed.id,
                content=content,
                occurred_at=occurred_at,
                items_scanned=claimed.items_scanned + batch_deleted,
                items_deleted=claimed.items_deleted + batch_deleted,
            )
            if paused:
                return

            batch_deleted += 1
            deletions_since_renewal += 1

        updated_run = replace(
            claimed,
            items_scanned=claimed.items_scanned + len(due),
            items_deleted=claimed.items_deleted + batch_deleted,
            updated_at=occurred_at,
            claim_token=claim_token,
            claim_expires_at=occurred_at + _CLAIM_LEASE,
        )

        uow = self._uow_factory()
        async with uow:
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=tenant_id,
                    expires_before=claimed.expires_before,
                    limit=1,
                )
            )
            if remaining:
                await uow.retention_purge_runs.update(purge_run=updated_run)
                continuation_job_id = self._uuid_factory()
                with suppress(DuplicateOutboxJobError):
                    await uow.outbox_jobs.enqueue(
                        build_outbox_job(
                            job_id=continuation_job_id,
                            tenant_id=tenant_id,
                            job_kind=OutboxJobKind.RETENTION_DELETE,
                            reference=OutboxJobReference(
                                resource_type="retention_purge_run",
                                resource_id=claimed.id,
                                schema_version=1,
                                tenant_id=tenant_id,
                            ),
                            deduplication_key=(
                                f"retention_purge_{claimed.id}_cont_{updated_run.items_deleted}"
                            ),
                            created_at=occurred_at,
                        )
                    )
            else:
                completed = replace(
                    updated_run,
                    status=RetentionPurgeRunStatus.COMPLETED,
                    completed_at=occurred_at,
                    claim_token=None,
                    claim_expires_at=None,
                )
                await uow.retention_purge_runs.update(purge_run=completed)
            await uow.commit()

    async def _maybe_renew_claim(
        self,
        *,
        claimed: RetentionPurgeRun,
        claim_token: UUID,
        occurred_at: datetime,
        deletions_since_renewal: int,
    ) -> RetentionPurgeRun:
        if claimed.claim_expires_at is None:
            return claimed
        remaining = claimed.claim_expires_at - occurred_at
        needs_renewal = (
            remaining <= _CLAIM_LEASE / 3 or deletions_since_renewal >= _RENEW_AFTER_DELETIONS
        )
        if not needs_renewal:
            return claimed

        uow = self._uow_factory()
        async with uow:
            renewed = await uow.retention_purge_runs.renew_claim(
                tenant_id=claimed.tenant_id,
                purge_run_id=claimed.id,
                claim_token=claim_token,
                claim_expires_at=occurred_at + _CLAIM_LEASE,
                now=occurred_at,
                expected_version=claimed.version,
            )
            await uow.commit()
        if renewed is None:
            raise RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.STALE_CLAIM,
                permanent=False,
            )
        return renewed

    async def _delete_content_under_lock(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        content: EncryptedContent,
        occurred_at: datetime,
        items_scanned: int,
        items_deleted: int,
    ) -> bool:
        uow = self._uow_factory()
        async with uow:
            await uow.retention_purge_runs.acquire_tenant_retention_lock(tenant_id=tenant_id)
            if await uow.legal_holds.tenant_has_active_hold(tenant_id=tenant_id):
                await uow.rollback()
                await self._mark_run_paused(
                    tenant_id=tenant_id,
                    purge_run_id=purge_run_id,
                    occurred_at=occurred_at,
                    skipped=True,
                    items_scanned=items_scanned,
                    items_deleted=items_deleted,
                )
                return True

            batch = RetentionPurgeBatch(
                id=self._uuid_factory(),
                tenant_id=tenant_id,
                purge_run_id=purge_run_id,
                deleted_content_id=content.id,
                status=RetentionPurgeBatchStatus.PENDING,
                created_at=occurred_at,
            )
            await uow.retention_purge_batches.add(batch=batch)
            await uow.encrypted_contents.delete(
                tenant_id=tenant_id,
                content_id=content.id,
            )
            await uow.retention_purge_batches.update_status(
                tenant_id=tenant_id,
                batch_id=batch.id,
                status=RetentionPurgeBatchStatus.COMPLETED,
                completed_at=occurred_at,
            )
            await uow.commit()
        return False

    async def _claim_run(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        claim_token: UUID,
        occurred_at: datetime,
    ) -> RetentionPurgeRun | None:
        uow = self._uow_factory()
        async with uow:
            existing = await uow.retention_purge_runs.get_by_id(
                tenant_id=tenant_id,
                purge_run_id=purge_run_id,
            )
            if existing is None:
                raise RetentionPurgeHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            if existing.status in {
                RetentionPurgeRunStatus.COMPLETED,
                RetentionPurgeRunStatus.CANCELLED,
                RetentionPurgeRunStatus.PAUSED,
            }:
                return existing
            claimed = await uow.retention_purge_runs.try_claim(
                tenant_id=tenant_id,
                purge_run_id=purge_run_id,
                claim_token=claim_token,
                claim_expires_at=occurred_at + _CLAIM_LEASE,
                now=occurred_at,
                expected_version=existing.version,
            )
            await uow.commit()
            return claimed

    async def _mark_run_paused(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        occurred_at: datetime,
        skipped: bool,
        items_scanned: int | None = None,
        items_deleted: int | None = None,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            purge_run = await uow.retention_purge_runs.get_by_id(
                tenant_id=tenant_id,
                purge_run_id=purge_run_id,
            )
            if purge_run is None:
                return
            paused = replace(
                purge_run,
                status=RetentionPurgeRunStatus.PAUSED,
                items_skipped_legal_hold=purge_run.items_skipped_legal_hold + (1 if skipped else 0),
                items_scanned=items_scanned
                if items_scanned is not None
                else purge_run.items_scanned,
                items_deleted=items_deleted
                if items_deleted is not None
                else purge_run.items_deleted,
                claim_token=None,
                claim_expires_at=None,
                updated_at=occurred_at,
                last_error_code="legal_hold_active",
            )
            await uow.retention_purge_runs.update(purge_run=paused)
            await uow.commit()


__all__ = ["RetentionPurgeHandler", "RetentionPurgeHandlerError"]
