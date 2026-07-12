"""PostgreSQL integration tests for transactional outbox repositories."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.outbox_persistence import (
    DuplicateOutboxJobError,
    OutboxClaimMismatchError,
    OutboxReconciliationFilter,
)
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)

from tests.encryption_support import NOW, OUTBOX_JOB_B_ID, OUTBOX_JOB_ID
from tests.tenant_persistence_support import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.hi_persistence

RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")


def _build_job(
    *,
    job_id: UUID = OUTBOX_JOB_ID,
    tenant_id: UUID | None = TENANT_A_ID,
    deduplication_key: str = "content_redact_synthetic",
    priority: int = 100,
    available_at: datetime | None = None,
) -> OutboxJob:
    reference = OutboxJobReference(
        tenant_id=tenant_id,
        resource_type="message",
        resource_id=RESOURCE_ID,
        schema_version=1,
    )
    if available_at is not None:
        return build_outbox_job(
            job_id=job_id,
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=reference,
            deduplication_key=deduplication_key,
            created_at=NOW,
            priority=priority,
            available_at=available_at,
        )
    return build_outbox_job(
        job_id=job_id,
        tenant_id=tenant_id,
        job_kind=OutboxJobKind.CONTENT_REDACT,
        reference=reference,
        deduplication_key=deduplication_key,
        created_at=NOW,
        priority=priority,
    )


async def _enqueue(integrated_uow_factory: Any, job: OutboxJob) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.outbox_jobs.enqueue(job)
        await uow.commit()


def test_outbox_enqueue_and_get_by_id(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        job = _build_job()
        await _enqueue(integrated_uow_factory, job)
        uow = integrated_uow_factory()
        async with uow:
            restored = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
        assert restored is not None
        assert restored.state is OutboxJobState.PENDING
        assert restored.deduplication_key == "content_redact_synthetic"

    asyncio.run(exercise())


def test_outbox_enqueue_rejects_duplicate_deduplication_key(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(DuplicateOutboxJobError):
                await uow.outbox_jobs.enqueue(
                    _build_job(job_id=OUTBOX_JOB_B_ID, deduplication_key="content_redact_synthetic")
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_outbox_get_or_create_returns_existing(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        job = _build_job()
        await _enqueue(integrated_uow_factory, job)
        uow = integrated_uow_factory()
        async with uow:
            restored, created = await uow.outbox_jobs.get_or_create(
                _build_job(job_id=uuid4(), deduplication_key="content_redact_synthetic")
            )
        assert created is False
        assert restored.id == OUTBOX_JOB_ID

    asyncio.run(exercise())


def test_outbox_claim_publisher_batch(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=5,
            )
            await uow.commit()
        assert len(claimed) == 1
        assert claimed[0].state is OutboxJobState.PUBLISHING
        assert claimed[0].claimed_by == "publisher-a"

    asyncio.run(exercise())


def test_outbox_claim_publisher_batch_skip_locked_concurrency(
    integrated_uow_factory: Any,
    auth_session_factory: Any,
) -> None:
    async def exercise() -> None:
        for index in range(3):
            await _enqueue(
                integrated_uow_factory,
                _build_job(
                    job_id=UUID(f"00000000-0000-0000-0000-00000000c0{index + 10:02x}"),
                    deduplication_key=f"content_redact_{index}",
                ),
            )

        from closeros.infrastructure.outbox_repositories import SqlAlchemyOutboxJobRepository

        async def claim(worker_id: str) -> tuple[UUID, ...]:
            session = auth_session_factory()
            async with session.begin():
                repository = SqlAlchemyOutboxJobRepository(session)
                claimed = await repository.claim_publisher_batch(
                    worker_id=worker_id,
                    now=NOW,
                    batch_size=2,
                )
            return tuple(job.id for job in claimed)

        first_ids, second_ids = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        assert first_ids
        assert second_ids
        assert set(first_ids).isdisjoint(set(second_ids))
        assert len(set(first_ids) | set(second_ids)) >= 2

    asyncio.run(exercise())


def test_outbox_mark_published(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            published = await uow.outbox_jobs.mark_published(
                job_id=job.id,
                claim_token=job.claim_token,
                now=NOW,
                expected_version=job.version,
            )
            await uow.commit()
        assert published.state is OutboxJobState.PUBLISHED

    asyncio.run(exercise())


def test_outbox_mark_published_rejects_stale_claim_token(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            with pytest.raises(OutboxClaimMismatchError):
                await uow.outbox_jobs.mark_published(
                    job_id=job.id,
                    claim_token=uuid4(),
                    now=NOW,
                    expected_version=job.version,
                )

    asyncio.run(exercise())


def test_outbox_schedule_retry(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            retried = await uow.outbox_jobs.schedule_retry(
                job_id=job.id,
                claim_token=job.claim_token,
                error_code=OutboxErrorCode.QUEUE_UNAVAILABLE.value,
                now=NOW,
                expected_version=job.version,
                phase=OutboxJobPhase.PUBLISHER.value,
            )
            await uow.commit()
        assert retried.state is OutboxJobState.RETRY_SCHEDULED
        assert retried.attempt_count == 1

    asyncio.run(exercise())


def test_outbox_mark_dead_letter(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            dead = await uow.outbox_jobs.mark_dead_letter(
                job_id=job.id,
                claim_token=job.claim_token,
                error_code=OutboxErrorCode.MAX_ATTEMPTS_EXCEEDED.value,
                now=NOW,
                expected_version=job.version,
            )
            await uow.commit()
        assert dead.state is OutboxJobState.DEAD_LETTER

    asyncio.run(exercise())


def test_outbox_claim_for_processing(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            await uow.outbox_jobs.mark_published(
                job_id=job.id,
                claim_token=job.claim_token,
                now=NOW,
                expected_version=job.version,
            )
            processing = await uow.outbox_jobs.claim_for_processing(
                job_id=job.id,
                worker_id="processor-a",
                now=NOW,
            )
            await uow.commit()
        assert processing is not None
        assert processing.state is OutboxJobState.PROCESSING

    asyncio.run(exercise())


def test_outbox_mark_succeeded(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            job = claimed[0]
            await uow.outbox_jobs.mark_published(
                job_id=job.id,
                claim_token=job.claim_token,
                now=NOW,
                expected_version=job.version,
            )
            processing = await uow.outbox_jobs.claim_for_processing(
                job_id=job.id,
                worker_id="processor-a",
                now=NOW,
            )
            assert processing is not None
            succeeded = await uow.outbox_jobs.mark_succeeded(
                job_id=processing.id,
                claim_token=processing.claim_token,
                now=NOW,
                expected_version=processing.version,
            )
            await uow.commit()
        assert succeeded.state is OutboxJobState.SUCCEEDED

    asyncio.run(exercise())


def test_outbox_recover_expired_publisher_claim(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        expired_now = NOW - timedelta(hours=2)
        await _enqueue(
            integrated_uow_factory,
            _build_job(available_at=expired_now),
        )
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=expired_now,
                batch_size=1,
            )
            assert len(claimed) == 1
            await uow.commit()
        recover_uow = integrated_uow_factory()
        async with recover_uow:
            recovered = await recover_uow.outbox_jobs.recover_expired_claims(now=NOW)
            await recover_uow.commit()
        assert len(recovered) == 1
        assert recovered[0].state is OutboxJobState.PENDING

    asyncio.run(exercise())


def test_outbox_recover_expired_processor_claim(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        expired_now = NOW - timedelta(hours=2)
        await _enqueue(
            integrated_uow_factory,
            _build_job(available_at=expired_now),
        )
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=expired_now,
                batch_size=1,
            )
            job = claimed[0]
            await uow.outbox_jobs.mark_published(
                job_id=job.id,
                claim_token=job.claim_token,
                now=expired_now,
                expected_version=job.version,
            )
            processing = await uow.outbox_jobs.claim_for_processing(
                job_id=job.id,
                worker_id="processor-a",
                now=expired_now,
            )
            assert processing is not None
            await uow.commit()
        recover_uow = integrated_uow_factory()
        async with recover_uow:
            recovered = await recover_uow.outbox_jobs.recover_expired_claims(now=NOW)
            await recover_uow.commit()
        assert len(recovered) == 1
        assert recovered[0].state is OutboxJobState.PUBLISHED

    asyncio.run(exercise())


def test_outbox_list_by_state(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _enqueue(integrated_uow_factory, _build_job())
        uow = integrated_uow_factory()
        async with uow:
            pending = await uow.outbox_jobs.list_by_state(
                state=OutboxJobState.PENDING,
                query_filter=OutboxReconciliationFilter(limit=10),
            )
        assert len(pending) == 1

    asyncio.run(exercise())


def test_outbox_global_job_deduplication(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        global_job = build_outbox_job(
            job_id=uuid4(),
            tenant_id=None,
            job_kind=OutboxJobKind.RECONCILIATION_RUN,
            reference=OutboxJobReference(
                resource_type="reconciliation",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="reconciliation_run",
            created_at=NOW,
        )
        await _enqueue(integrated_uow_factory, global_job)
        uow = integrated_uow_factory()
        async with uow:
            restored = await uow.outbox_jobs.get_by_id(job_id=global_job.id)
        assert restored is not None
        assert restored.tenant_id is None

    asyncio.run(exercise())


def test_outbox_tenant_scoped_deduplication_isolated_by_tenant(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _enqueue(
            integrated_uow_factory,
            _build_job(tenant_id=TENANT_A_ID, deduplication_key="shared_key"),
        )
        tenant_b_job = _build_job(
            job_id=OUTBOX_JOB_B_ID,
            tenant_id=TENANT_B_ID,
            deduplication_key="shared_key",
        )
        await _enqueue(integrated_uow_factory, tenant_b_job)
        uow = integrated_uow_factory()
        async with uow:
            tenant_a = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_ID)
            tenant_b = await uow.outbox_jobs.get_by_id(job_id=OUTBOX_JOB_B_ID)
        assert tenant_a is not None
        assert tenant_b is not None

    asyncio.run(exercise())
