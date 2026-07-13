"""Tests for current analysis enqueue contract (outbox-level)."""

# mypy: disable-error-code=unused-ignore

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from closeros.application.outbox_processor import OutboxProcessorService
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)
from closeros_worker.runtime import NOPQ_SUPPORTED_JOB_KINDS, XY_SUPPORTED_JOB_KINDS

from tests.encryption_support import NOW

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000501")
JOB_ID = UUID("00000000-0000-0000-0000-000000000502")


def _enqueue_candidate() -> object:
    return build_outbox_job(
        job_id=JOB_ID,
        tenant_id=TENANT_ID,
        job_kind=OutboxJobKind.MESSAGE_ANALYZE,
        reference=OutboxJobReference(
            tenant_id=TENANT_ID,
            resource_type="conversation_thread",
            resource_id=THREAD_ID,
            schema_version=1,
        ),
        deduplication_key="analysis_enqueue_synthetic",
        created_at=NOW,
    )


def test_message_analyze_is_in_xy_worker_supported_kinds() -> None:
    assert OutboxJobKind.MESSAGE_ANALYZE in XY_SUPPORTED_JOB_KINDS


def test_notification_deliver_is_in_xy_worker_supported_kinds() -> None:
    assert OutboxJobKind.NOTIFICATION_DELIVER in XY_SUPPORTED_JOB_KINDS


def test_notification_deliver_is_not_in_nopq_worker_supported_kinds() -> None:
    assert OutboxJobKind.NOTIFICATION_DELIVER not in NOPQ_SUPPORTED_JOB_KINDS


def test_enqueue_candidate_is_tenant_scoped_and_starts_pending() -> None:
    job = _enqueue_candidate()
    assert job.tenant_id == TENANT_ID  # type: ignore[attr-defined]
    assert job.job_kind is OutboxJobKind.MESSAGE_ANALYZE  # type: ignore[attr-defined]
    assert job.state is OutboxJobState.PENDING  # type: ignore[attr-defined]


def test_nopq_processor_does_not_claim_unsupported_notification_jobs(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                build_outbox_job(
                    job_id=JOB_ID,
                    tenant_id=TENANT_ID,
                    job_kind=OutboxJobKind.NOTIFICATION_DELIVER,
                    reference=OutboxJobReference(
                        tenant_id=TENANT_ID,
                        resource_type="conversation_thread",
                        resource_id=THREAD_ID,
                        schema_version=1,
                    ),
                    deduplication_key="notification_enqueue_unsupported_test",
                    created_at=NOW,
                )
            )
            await uow.commit()
        uow = integrated_uow_factory()
        async with uow:
            processor = OutboxProcessorService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                handlers={},
                worker_id="analysis-enqueue-test-worker",
                supported_job_kinds=NOPQ_SUPPORTED_JOB_KINDS,
            )
            result = await processor.process_job(job_id=JOB_ID, now=NOW)
            persisted = await uow.outbox_jobs.get_by_id(job_id=JOB_ID)
        assert result.outcome == "not_claimed"
        assert persisted is not None
        assert persisted.state is OutboxJobState.PENDING

    asyncio.run(exercise())
