"""Unit tests for XY handler error classification in OutboxProcessorService."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from closeros.application.media_fetch_handler import MediaFetchHandlerError
from closeros.application.media_scan_handler import MediaScanHandlerError
from closeros.application.notification_deliver_handler import NotificationDeliverHandlerError
from closeros.application.optional_feature_handler import OptionalFeatureDisabledHandlerError
from closeros.application.outbox_processor import OutboxJobHandler, OutboxProcessorService
from closeros.application.retention_purge_handler import RetentionPurgeHandlerError
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)

from tests.encryption_support import NOW, OUTBOX_JOB_ID

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")


class _RaisingHandler:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def handle(self, *, job: object) -> None:
        raise self._error


class _SuccessHandler:
    async def handle(self, *, job: object) -> None:
        return None


def _processing_job(*, job_kind: OutboxJobKind, max_attempts: int = 10) -> OutboxJob:
    return build_outbox_job(
        job_id=OUTBOX_JOB_ID,
        tenant_id=TENANT_ID,
        job_kind=job_kind,
        reference=OutboxJobReference(
            tenant_id=TENANT_ID,
            resource_type="resource",
            resource_id=RESOURCE_ID,
            schema_version=1,
        ),
        deduplication_key=f"xy_outbox_error_{job_kind.value.replace('.', '_')}",
        created_at=NOW,
        max_attempts=max_attempts,
    )


def _claimed_job(job: OutboxJob) -> OutboxJob:
    claim_token = uuid4()
    return replace(
        job,
        state=OutboxJobState.PROCESSING,
        claim_token=claim_token,
        claimed_by="processor-test",
        claimed_at=NOW,
        claim_expires_at=NOW + timedelta(minutes=5),
        version=1,
    )


def _build_processor(
    *,
    handler: OutboxJobHandler,
    job_kind: OutboxJobKind,
    max_attempts: int = 10,
) -> tuple[OutboxProcessorService, AsyncMock, AsyncMock, OutboxJob]:
    job = _processing_job(job_kind=job_kind, max_attempts=max_attempts)
    claimed = _claimed_job(job)

    outbox_jobs = AsyncMock()
    outbox_job_attempts = AsyncMock()
    outbox_jobs.claim_for_processing = AsyncMock(return_value=claimed)
    outbox_jobs.renew_processor_claim = AsyncMock(return_value=claimed)
    outbox_jobs.schedule_retry = AsyncMock(
        return_value=replace(claimed, state=OutboxJobState.RETRY_SCHEDULED)
    )
    outbox_jobs.mark_dead_letter = AsyncMock(
        return_value=replace(claimed, state=OutboxJobState.DEAD_LETTER)
    )
    outbox_jobs.mark_succeeded = AsyncMock(
        return_value=replace(claimed, state=OutboxJobState.SUCCEEDED)
    )
    outbox_job_attempts.append = AsyncMock()

    processor = OutboxProcessorService(
        outbox_jobs=outbox_jobs,
        outbox_job_attempts=outbox_job_attempts,
        handlers={job_kind: handler},
        worker_id="processor-test",
    )
    return processor, outbox_jobs, outbox_job_attempts, claimed


async def _process(
    *,
    handler: OutboxJobHandler,
    job_kind: OutboxJobKind,
    max_attempts: int = 10,
) -> tuple[str, AsyncMock, AsyncMock]:
    processor, outbox_jobs, outbox_job_attempts, _ = _build_processor(
        handler=handler,
        job_kind=job_kind,
        max_attempts=max_attempts,
    )
    result = await processor.process_job(job_id=OUTBOX_JOB_ID, now=NOW)
    return result.outcome, outbox_jobs, outbox_job_attempts


@pytest.mark.parametrize(
    ("error", "job_kind"),
    [
        (
            NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ),
            OutboxJobKind.NOTIFICATION_DELIVER,
        ),
        (
            MediaFetchHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ),
            OutboxJobKind.MEDIA_FETCH,
        ),
        (
            MediaScanHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=False,
            ),
            OutboxJobKind.MEDIA_SCAN,
        ),
        (
            RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.STALE_CLAIM,
                permanent=False,
            ),
            OutboxJobKind.RETENTION_DELETE,
        ),
    ],
)
def test_processor_retries_transient_typed_handler_errors(
    error: Exception,
    job_kind: OutboxJobKind,
) -> None:
    async def exercise() -> None:
        outcome, outbox_jobs, _ = await _process(
            handler=_RaisingHandler(error),
            job_kind=job_kind,
        )
        assert outcome == "retried"
        outbox_jobs.schedule_retry.assert_awaited_once()
        outbox_jobs.mark_dead_letter.assert_not_awaited()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("error", "job_kind"),
    [
        (
            NotificationDeliverHandlerError(
                error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                permanent=True,
            ),
            OutboxJobKind.NOTIFICATION_DELIVER,
        ),
        (
            MediaFetchHandlerError(
                error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                permanent=True,
            ),
            OutboxJobKind.MEDIA_FETCH,
        ),
        (
            MediaScanHandlerError(
                error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                permanent=True,
            ),
            OutboxJobKind.MEDIA_SCAN,
        ),
        (
            RetentionPurgeHandlerError(
                error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                permanent=True,
            ),
            OutboxJobKind.RETENTION_DELETE,
        ),
    ],
)
def test_processor_dead_letters_permanent_typed_handler_errors(
    error: Exception,
    job_kind: OutboxJobKind,
) -> None:
    async def exercise() -> None:
        outcome, outbox_jobs, _ = await _process(
            handler=_RaisingHandler(error),
            job_kind=job_kind,
        )
        assert outcome == "dead_lettered"
        outbox_jobs.mark_dead_letter.assert_awaited_once()
        outbox_jobs.schedule_retry.assert_not_awaited()

    asyncio.run(exercise())


def test_processor_dead_letters_optional_feature_disabled_error() -> None:
    async def exercise() -> None:
        outcome, outbox_jobs, _ = await _process(
            handler=_RaisingHandler(OptionalFeatureDisabledHandlerError()),
            job_kind=OutboxJobKind.CRM_SYNC,
        )
        assert outcome == "dead_lettered"
        outbox_jobs.mark_dead_letter.assert_awaited_once()
        outbox_jobs.schedule_retry.assert_not_awaited()

    asyncio.run(exercise())


def test_processor_succeeds_when_handler_completes_normally() -> None:
    async def exercise() -> None:
        outcome, outbox_jobs, outbox_job_attempts = await _process(
            handler=_SuccessHandler(),
            job_kind=OutboxJobKind.MEDIA_SCAN,
        )
        assert outcome == "succeeded"
        outbox_jobs.mark_succeeded.assert_awaited_once()
        outbox_jobs.schedule_retry.assert_not_awaited()
        outbox_jobs.mark_dead_letter.assert_not_awaited()
        outbox_job_attempts.append.assert_awaited()

    asyncio.run(exercise())
