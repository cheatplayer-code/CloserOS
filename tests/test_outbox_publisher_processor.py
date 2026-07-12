"""Unit tests for outbox publisher and processor services."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.outbox_processor import (
    NoOpOutboxJobHandler,
    OutboxProcessorService,
    build_noop_handlers,
)
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)

from tests.encryption_support import NOW, OUTBOX_JOB_ID

pytestmark = pytest.mark.hi_persistence

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")


class RecordingQueuePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.published_job_ids: list[UUID] = []
        self._fail = fail

    async def publish_job_id(self, *, job_id: UUID) -> None:
        if self._fail:
            raise RuntimeError("queue unavailable")
        self.published_job_ids.append(job_id)


class FailingHandler:
    async def handle(self, *, job: OutboxJob) -> None:
        raise RuntimeError("handler failed")


def _pending_job(*, max_attempts: int = 10) -> OutboxJob:
    return build_outbox_job(
        job_id=OUTBOX_JOB_ID,
        tenant_id=TENANT_A,
        job_kind=OutboxJobKind.CONTENT_REDACT,
        reference=OutboxJobReference(
            tenant_id=TENANT_A,
            resource_type="message",
            resource_id=RESOURCE_ID,
            schema_version=1,
        ),
        deduplication_key="content_redact_publisher_test",
        created_at=NOW,
        max_attempts=max_attempts,
    )


async def _seed_pending_job(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.outbox_jobs.enqueue(_pending_job())
        await uow.commit()


def test_publisher_publishes_uuid_only(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher()
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            result = await publisher.publish_batch(now=NOW, batch_size=5)
            await uow.commit()
        assert result.published_count == 1
        assert queue.published_job_ids == [OUTBOX_JOB_ID]

    asyncio.run(exercise())


def test_publisher_marks_job_published(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher()
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            restored = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await uow.commit()
        assert restored is not None
        assert restored.state is OutboxJobState.PUBLISHED

    asyncio.run(exercise())


def test_publisher_schedules_retry_on_queue_failure(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher(fail=True)
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            result = await publisher.publish_batch(now=NOW, batch_size=5)
            restored = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await uow.commit()
        assert result.retried_count == 1
        assert restored is not None
        assert restored.state is OutboxJobState.RETRY_SCHEDULED
        assert restored.last_error_code is OutboxErrorCode.QUEUE_UNAVAILABLE

    asyncio.run(exercise())


def test_publisher_dead_letters_when_retry_budget_exhausted(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                build_outbox_job(
                    job_id=OUTBOX_JOB_ID,
                    tenant_id=TENANT_A,
                    job_kind=OutboxJobKind.CONTENT_REDACT,
                    reference=OutboxJobReference(
                        tenant_id=TENANT_A,
                        resource_type="message",
                        resource_id=RESOURCE_ID,
                        schema_version=1,
                    ),
                    deduplication_key="content_redact_dead_letter",
                    created_at=NOW,
                    max_attempts=1,
                )
            )
            await uow.commit()
        queue = RecordingQueuePublisher(fail=True)
        publish_uow = integrated_uow_factory()
        async with publish_uow:
            publisher = OutboxPublisherService(
                outbox_jobs=publish_uow.outbox_jobs,
                outbox_job_attempts=publish_uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            result = await publisher.publish_batch(now=NOW, batch_size=5)
            restored = await publish_uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await publish_uow.commit()
        assert result.dead_lettered_count == 1
        assert restored is not None
        assert restored.state is OutboxJobState.DEAD_LETTER

    asyncio.run(exercise())


def test_processor_succeeds_with_noop_handler(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher()
        publish_uow = integrated_uow_factory()
        async with publish_uow:
            publisher = OutboxPublisherService(
                outbox_jobs=publish_uow.outbox_jobs,
                outbox_job_attempts=publish_uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            await publish_uow.commit()
        process_uow = integrated_uow_factory()
        async with process_uow:
            processor = OutboxProcessorService(
                outbox_jobs=process_uow.outbox_jobs,
                outbox_job_attempts=process_uow.outbox_job_attempts,
                handlers=build_noop_handlers(),
                worker_id="processor-a",
            )
            result = await processor.process_job(job_id=OUTBOX_JOB_ID, now=NOW)
            restored = await process_uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await process_uow.commit()
        assert result.outcome == "succeeded"
        assert restored is not None
        assert restored.state is OutboxJobState.SUCCEEDED

    asyncio.run(exercise())


def test_processor_retries_on_handler_failure(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher()
        publish_uow = integrated_uow_factory()
        async with publish_uow:
            publisher = OutboxPublisherService(
                outbox_jobs=publish_uow.outbox_jobs,
                outbox_job_attempts=publish_uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            await publish_uow.commit()
        process_uow = integrated_uow_factory()
        async with process_uow:
            processor = OutboxProcessorService(
                outbox_jobs=process_uow.outbox_jobs,
                outbox_job_attempts=process_uow.outbox_job_attempts,
                handlers={OutboxJobKind.CONTENT_REDACT: FailingHandler()},
                worker_id="processor-a",
            )
            result = await processor.process_job(job_id=OUTBOX_JOB_ID, now=NOW)
            restored = await process_uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await process_uow.commit()
        assert result.outcome == "retried"
        assert restored is not None
        assert restored.state is OutboxJobState.RETRY_SCHEDULED

    asyncio.run(exercise())


def test_processor_not_claimed_when_job_not_published(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        uow = integrated_uow_factory()
        async with uow:
            processor = OutboxProcessorService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                handlers=build_noop_handlers(),
                worker_id="processor-a",
            )
            result = await processor.process_job(job_id=OUTBOX_JOB_ID, now=NOW)
        assert result.outcome == "not_claimed"

    asyncio.run(exercise())


def test_noop_handler_supports_all_job_kinds() -> None:
    handler = NoOpOutboxJobHandler()
    job = build_outbox_job(
        job_id=uuid4(),
        tenant_id=None,
        job_kind=OutboxJobKind.RECONCILIATION_RUN,
        reference=OutboxJobReference(
            resource_type="reconciliation",
            resource_id=RESOURCE_ID,
            schema_version=1,
        ),
        deduplication_key="reconciliation_noop",
        created_at=NOW,
    )

    async def exercise() -> None:
        await handler.handle(job=job)

    asyncio.run(exercise())


def test_publisher_records_attempt_on_success(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_pending_job(integrated_uow_factory)
        queue = RecordingQueuePublisher()
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            await uow.commit()
        lookup = integrated_uow_factory()
        async with lookup:
            job = await lookup.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            assert job is not None

    asyncio.run(exercise())


def test_processor_dead_letters_after_max_attempts(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                build_outbox_job(
                    job_id=OUTBOX_JOB_ID,
                    tenant_id=TENANT_A,
                    job_kind=OutboxJobKind.CONTENT_REDACT,
                    reference=OutboxJobReference(
                        tenant_id=TENANT_A,
                        resource_type="message",
                        resource_id=RESOURCE_ID,
                        schema_version=1,
                    ),
                    deduplication_key="content_redact_processor_dead",
                    created_at=NOW,
                    max_attempts=1,
                )
            )
            await uow.commit()
        queue = RecordingQueuePublisher()
        publish_uow = integrated_uow_factory()
        async with publish_uow:
            publisher = OutboxPublisherService(
                outbox_jobs=publish_uow.outbox_jobs,
                outbox_job_attempts=publish_uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="publisher-a",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            await publish_uow.commit()
        process_uow = integrated_uow_factory()
        async with process_uow:
            processor = OutboxProcessorService(
                outbox_jobs=process_uow.outbox_jobs,
                outbox_job_attempts=process_uow.outbox_job_attempts,
                handlers={OutboxJobKind.CONTENT_REDACT: FailingHandler()},
                worker_id="processor-a",
            )
            result = await processor.process_job(job_id=OUTBOX_JOB_ID, now=NOW)
            restored = await process_uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            await process_uow.commit()
        assert result.outcome == "dead_lettered"
        assert restored is not None
        assert restored.state is OutboxJobState.DEAD_LETTER

    asyncio.run(exercise())
