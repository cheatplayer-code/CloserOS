"""Worker runtime tests for LM redaction and metrics handlers."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.application.content_redact_handler import ContentRedactHandler
from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandler
from closeros.application.outbox_processor import OutboxProcessorService
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)
from closeros.infrastructure.database import (
    create_authentication_engine,
)
from closeros_worker.runtime import (
    LM_SUPPORTED_JOB_KINDS,
    WorkerRuntimeOverrides,
    build_worker_runtime,
)
from closeros_worker.settings import WorkerSettings
from redis.asyncio import Redis

from tests.encryption_support import NOW, SERVICE_ID

pytestmark = pytest.mark.lm_persistence

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")
UNSUPPORTED_JOB_ID = UUID("00000000-0000-0000-0000-000000000200")


class _NoopRedis:
    async def aclose(self) -> None:
        return None


class RecordingQueuePublisher:
    def __init__(self) -> None:
        self.published_job_ids: list[UUID] = []

    async def publish_job_id(self, *, job_id: UUID) -> None:
        self.published_job_ids.append(job_id)

    async def close(self) -> None:
        return None


def test_lm_supported_job_kinds_include_redaction_and_metrics() -> None:
    assert OutboxJobKind.CONTENT_REDACT in LM_SUPPORTED_JOB_KINDS
    assert OutboxJobKind.METRICS_RECALCULATE in LM_SUPPORTED_JOB_KINDS
    assert OutboxJobKind.WEBHOOK_NORMALIZE in LM_SUPPORTED_JOB_KINDS
    assert OutboxJobKind.CSV_IMPORT in LM_SUPPORTED_JOB_KINDS


def test_lm_worker_runtime_registers_redact_and_recalculate_handlers(
    auth_test_database_url: str,
    auth_session_factory: Any,
) -> None:
    engine = create_authentication_engine(auth_test_database_url)
    settings = WorkerSettings(
        app_env="development",
        database_url=auth_test_database_url,
        redis_url="redis://127.0.0.1:6379/0",
        outbox_stream="closeros.outbox.jobs",
        outbox_consumer_group="closeros.outbox.processors",
        worker_id="lm-worker-test",
        polling_interval_seconds=1.0,
        publish_batch_size=25,
        processor_block_ms=5_000,
    )

    async def exercise() -> None:
        runtime = build_worker_runtime(
            settings,
            overrides=WorkerRuntimeOverrides(
                engine=engine,
                session_factory=auth_session_factory,
                redis=cast(Redis, _NoopRedis()),
                ingestion_service_id=SERVICE_ID,
            ),
        )
        try:
            assert OutboxJobKind.CONTENT_REDACT in runtime.handlers
            assert OutboxJobKind.METRICS_RECALCULATE in runtime.handlers
            assert isinstance(runtime.handlers[OutboxJobKind.CONTENT_REDACT], ContentRedactHandler)
            assert isinstance(
                runtime.handlers[OutboxJobKind.METRICS_RECALCULATE],
                MetricsRecalculateHandler,
            )
        finally:
            await runtime.dispose()

    asyncio.run(exercise())


def test_lm_processor_leaves_unsupported_job_kind_unclaimed(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            await uow.outbox_jobs.enqueue(
                build_outbox_job(
                    job_id=UNSUPPORTED_JOB_ID,
                    tenant_id=TENANT_A,
                    job_kind=OutboxJobKind.MESSAGE_ANALYZE,
                    reference=OutboxJobReference(
                        tenant_id=TENANT_A,
                        resource_type="message",
                        resource_id=RESOURCE_ID,
                        schema_version=1,
                    ),
                    deduplication_key="message_analyze_unsupported_test",
                    created_at=NOW,
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
                worker_id="lm-publisher-test",
            )
            await publisher.publish_batch(now=NOW, batch_size=5)
            await publish_uow.commit()

        process_uow = integrated_uow_factory()
        async with process_uow:
            processor = OutboxProcessorService(
                outbox_jobs=process_uow.outbox_jobs,
                outbox_job_attempts=process_uow.outbox_job_attempts,
                handlers={},
                worker_id="lm-processor-test",
                supported_job_kinds=LM_SUPPORTED_JOB_KINDS,
            )
            result = await processor.process_job(job_id=UNSUPPORTED_JOB_ID, now=NOW)
            restored = await process_uow.outbox_jobs.get_by_id(job_id=UNSUPPORTED_JOB_ID)
            await process_uow.commit()

        assert result.outcome == "not_claimed"
        assert restored is not None
        assert restored.state is OutboxJobState.PUBLISHED

    asyncio.run(exercise())
