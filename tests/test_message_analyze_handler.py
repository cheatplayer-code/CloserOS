"""Tests for current `message.analyze` handling contract in outbox pipeline."""

# mypy: disable-error-code=unused-ignore

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from closeros.application.outbox_processor import OutboxProcessorService, build_noop_handlers
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)

from tests.encryption_support import NOW

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
PUBLISH_JOB_ID = UUID("00000000-0000-0000-0000-000000000401")
PROCESS_JOB_ID = UUID("00000000-0000-0000-0000-000000000403")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000402")


class _Queue:
    def __init__(self) -> None:
        self.published: list[UUID] = []

    async def publish_job_id(self, *, job_id: UUID) -> None:
        self.published.append(job_id)


def _message_analyze_job(*, job_id: UUID, deduplication_key: str) -> object:
    return build_outbox_job(
        job_id=job_id,
        tenant_id=TENANT_ID,
        job_kind=OutboxJobKind.MESSAGE_ANALYZE,
        reference=OutboxJobReference(
            tenant_id=TENANT_ID,
            resource_type="message",
            resource_id=RESOURCE_ID,
            schema_version=1,
        ),
        deduplication_key=deduplication_key,
        created_at=NOW,
    )


def test_message_analyze_job_kind_is_defined_in_outbox_enum() -> None:
    assert OutboxJobKind.MESSAGE_ANALYZE.value == "message.analyze"


def test_message_analyze_can_be_published_without_payload_leak(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                _message_analyze_job(
                    job_id=PUBLISH_JOB_ID,
                    deduplication_key="message_analyze_publish_contract_test",
                )
            )  # type: ignore[arg-type]
            await uow.commit()
        queue = _Queue()
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="nopq-message-publisher",
            )
            await publisher.publish_batch(now=NOW, batch_size=10)
            job = await uow.outbox_jobs.get_by_id(job_id=PUBLISH_JOB_ID)
        assert queue.published == [PUBLISH_JOB_ID]
        assert job is not None
        assert job.state is OutboxJobState.PUBLISHED

    asyncio.run(exercise())


def test_message_analyze_is_processible_with_noop_handler_set(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                _message_analyze_job(
                    job_id=PROCESS_JOB_ID,
                    deduplication_key="message_analyze_process_contract_test",
                )
            )  # type: ignore[arg-type]
            await uow.commit()
        queue = _Queue()
        uow = integrated_uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=queue,
                worker_id="nopq-message-publisher",
            )
            await publisher.publish_batch(now=NOW, batch_size=10)
            await uow.commit()

        uow = integrated_uow_factory()
        async with uow:
            processor = OutboxProcessorService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                handlers=build_noop_handlers(),
                worker_id="nopq-message-processor",
            )
            result = await processor.process_job(job_id=PROCESS_JOB_ID, now=NOW)
            job = await uow.outbox_jobs.get_by_id(job_id=PROCESS_JOB_ID)
        assert result.outcome == "succeeded"
        assert job is not None and job.state is OutboxJobState.SUCCEEDED

    asyncio.run(exercise())
