"""Retention purge orchestration service."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from uuid import UUID

from closeros.application.encrypted_content_persistence import EncryptedContentRetentionFilter
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job
from closeros.domain.retention_execution import (
    RetentionPurgeRun,
    RetentionPurgeRunStatus,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class RetentionPurgeUnavailableError(Exception):
    """Raised when retention purge cannot be scheduled."""


class RetentionPurgeService:
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

    async def dry_run(
        self,
        *,
        tenant_id: UUID,
        expires_before: datetime,
        requested_at: datetime,
    ) -> RetentionPurgeRun:
        if await self._legal_hold_service.tenant_has_active_hold(tenant_id=tenant_id):
            return RetentionPurgeRun(
                id=self._uuid_factory(),
                tenant_id=tenant_id,
                status=RetentionPurgeRunStatus.COMPLETED,
                dry_run=True,
                expires_before=expires_before,
                items_scanned=0,
                items_deleted=0,
                items_skipped_legal_hold=0,
                started_at=requested_at,
                completed_at=requested_at,
                created_at=requested_at,
                updated_at=requested_at,
            )

        uow = self._uow_factory()
        async with uow:
            due_count = await uow.encrypted_contents.count_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=tenant_id,
                    expires_before=expires_before,
                )
            )

        return RetentionPurgeRun(
            id=self._uuid_factory(),
            tenant_id=tenant_id,
            status=RetentionPurgeRunStatus.COMPLETED,
            dry_run=True,
            expires_before=expires_before,
            items_scanned=due_count,
            items_deleted=0,
            items_skipped_legal_hold=0,
            started_at=requested_at,
            completed_at=requested_at,
            created_at=requested_at,
            updated_at=requested_at,
        )

    async def schedule_purge(
        self,
        *,
        tenant_id: UUID,
        expires_before: datetime,
        requested_at: datetime,
    ) -> UUID:
        if await self._legal_hold_service.tenant_has_active_hold(tenant_id=tenant_id):
            raise RetentionPurgeUnavailableError("tenant is under legal hold")

        purge_run_id = self._uuid_factory()
        job_id = self._uuid_factory()
        purge_run = RetentionPurgeRun(
            id=purge_run_id,
            tenant_id=tenant_id,
            status=RetentionPurgeRunStatus.PENDING,
            dry_run=False,
            expires_before=expires_before,
            items_scanned=0,
            items_deleted=0,
            items_skipped_legal_hold=0,
            started_at=None,
            completed_at=None,
            created_at=requested_at,
            updated_at=requested_at,
        )

        uow = self._uow_factory()
        async with uow:
            await uow.retention_purge_runs.add(purge_run=purge_run)
            with suppress(DuplicateOutboxJobError):
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.RETENTION_DELETE,
                        reference=OutboxJobReference(
                            resource_type="retention_purge_run",
                            resource_id=purge_run_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=f"retention_purge_{purge_run_id}",
                        created_at=requested_at,
                    )
                )
            await uow.commit()
        return purge_run_id

    async def get_purge_run(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
    ) -> RetentionPurgeRun | None:
        uow = self._uow_factory()
        async with uow:
            return await uow.retention_purge_runs.get_by_id(
                tenant_id=tenant_id,
                purge_run_id=purge_run_id,
            )


__all__ = ["RetentionPurgeService", "RetentionPurgeUnavailableError"]
