"""Application service for publishing transactional outbox jobs to the queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from closeros.application.outbox_persistence import (
    OutboxClaimMismatchError,
    OutboxJobAttemptRepository,
    OutboxJobRepository,
    OutboxPersistenceError,
)
from closeros.domain.outbox import (
    OutboxAttemptOutcome,
    OutboxErrorCode,
    OutboxJob,
    OutboxJobAttempt,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxTransitionError,
    schedule_retry,
)


class QueuePublisher(Protocol):
    async def publish_job_id(self, *, job_id: UUID) -> None: ...


class OutboxPublisherError(Exception):
    """Base class for safe outbox publisher failures."""


@dataclass(frozen=True, slots=True)
class OutboxPublisherResult:
    claimed_count: int
    published_count: int
    retried_count: int
    dead_lettered_count: int


class OutboxPublisherService:
    """Claims pending outbox jobs and publishes persisted UUIDs to the queue.

    Duplicate publication is expected: consumers must remain idempotent and load
    business data from PostgreSQL by persisted identifiers.
    """

    def __init__(
        self,
        *,
        outbox_jobs: OutboxJobRepository,
        outbox_job_attempts: OutboxJobAttemptRepository,
        queue_publisher: QueuePublisher,
        worker_id: str,
    ) -> None:
        self._outbox_jobs = outbox_jobs
        self._outbox_job_attempts = outbox_job_attempts
        self._queue_publisher = queue_publisher
        self._worker_id = worker_id

    async def publish_batch(
        self,
        *,
        now: datetime,
        batch_size: int,
        allowed_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> OutboxPublisherResult:
        claimed_jobs = await self._outbox_jobs.claim_publisher_batch(
            worker_id=self._worker_id,
            now=now,
            batch_size=batch_size,
            allowed_job_kinds=allowed_job_kinds,
        )
        published_count = 0
        retried_count = 0
        dead_lettered_count = 0

        for job in claimed_jobs:
            outcome = await self._publish_one(job=job, now=now)
            if outcome == "published":
                published_count += 1
            elif outcome == "retried":
                retried_count += 1
            else:
                dead_lettered_count += 1

        return OutboxPublisherResult(
            claimed_count=len(claimed_jobs),
            published_count=published_count,
            retried_count=retried_count,
            dead_lettered_count=dead_lettered_count,
        )

    async def _publish_one(self, *, job: OutboxJob, now: datetime) -> str:
        started_at = now
        try:
            await self._queue_publisher.publish_job_id(job_id=job.id)
        except Exception as error:
            return await self._handle_publish_failure(
                job=job,
                started_at=started_at,
                now=now,
                error_code=OutboxErrorCode.QUEUE_UNAVAILABLE,
                cause=error,
            )

        try:
            updated = await self._outbox_jobs.mark_published(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                now=now,
                expected_version=job.version,
            )
        except OutboxClaimMismatchError:
            await self._append_attempt(
                job=job,
                started_at=started_at,
                finished_at=now,
                outcome=OutboxAttemptOutcome.FAILED,
                error_code=OutboxErrorCode.STALE_CLAIM,
            )
            return "retried"
        except OutboxPersistenceError as error:
            return await self._handle_publish_failure(
                job=job,
                started_at=started_at,
                now=now,
                error_code=OutboxErrorCode.PUBLISH_FAILED,
                cause=error,
            )

        await self._append_attempt(
            job=updated,
            started_at=started_at,
            finished_at=now,
            outcome=OutboxAttemptOutcome.SUCCEEDED,
            error_code=None,
        )
        return "published"

    async def _handle_publish_failure(
        self,
        *,
        job: OutboxJob,
        started_at: datetime,
        now: datetime,
        error_code: OutboxErrorCode,
        cause: Exception,
    ) -> str:
        _ = cause
        await self._append_attempt(
            job=job,
            started_at=started_at,
            finished_at=now,
            outcome=OutboxAttemptOutcome.FAILED,
            error_code=error_code,
        )
        next_attempt_count = job.attempt_count + 1
        if next_attempt_count >= job.max_attempts:
            try:
                await self._outbox_jobs.mark_dead_letter(
                    job_id=job.id,
                    claim_token=job.claim_token,  # type: ignore[arg-type]
                    error_code=OutboxErrorCode.MAX_ATTEMPTS_EXCEEDED.value,
                    now=now,
                    expected_version=job.version,
                )
            except OutboxClaimMismatchError as error:
                raise OutboxPublisherError("outbox dead-letter finalization failed") from error
            return "dead_lettered"

        try:
            schedule_retry(
                job,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                phase=OutboxJobPhase.PUBLISHER,
                error_code=error_code,
                now=now,
                expected_version=job.version,
            )
        except OutboxTransitionError as error:
            raise OutboxPublisherError("outbox retry scheduling failed") from error

        try:
            await self._outbox_jobs.schedule_retry(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                error_code=error_code.value,
                now=now,
                expected_version=job.version,
                phase=OutboxJobPhase.PUBLISHER.value,
            )
        except OutboxClaimMismatchError as mismatch_error:
            raise OutboxPublisherError("outbox retry persistence failed") from mismatch_error
        return "retried"

    async def _append_attempt(
        self,
        *,
        job: OutboxJob,
        started_at: datetime,
        finished_at: datetime,
        outcome: OutboxAttemptOutcome,
        error_code: OutboxErrorCode | None,
    ) -> None:
        attempt = OutboxJobAttempt(
            id=uuid4(),
            job_id=job.id,
            attempt_number=max(job.attempt_count, 1),
            phase=OutboxJobPhase.PUBLISHER,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            claim_token=job.claim_token or uuid4(),
            error_code=error_code,
        )
        await self._outbox_job_attempts.append(attempt)
