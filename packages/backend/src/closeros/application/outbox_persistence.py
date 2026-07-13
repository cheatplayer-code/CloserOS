"""Application-layer persistence ports for the transactional outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.outbox import OutboxJob, OutboxJobAttempt, OutboxJobKind, OutboxJobState


class OutboxPersistenceError(PersistenceError):
    """Base class for safe outbox persistence failures."""


class OutboxRecordNotFoundError(OutboxPersistenceError):
    """Raised when an outbox job does not exist."""


class DuplicateOutboxJobError(OutboxPersistenceError):
    """Raised when a deduplication key already exists."""


class OutboxStaleVersionError(OutboxPersistenceError):
    """Raised when optimistic concurrency rejects an update."""


class OutboxClaimMismatchError(OutboxPersistenceError):
    """Raised when claim token, lease, or state does not match."""


@dataclass(frozen=True, slots=True)
class OutboxReconciliationFilter:
    tenant_id: UUID | None = None
    overdue_before: datetime | None = None
    limit: int = 100


class OutboxJobRepository(Protocol):
    async def enqueue(self, job: OutboxJob) -> None: ...

    async def get_by_id(self, *, job_id: UUID) -> OutboxJob | None: ...

    async def get_or_create(self, job: OutboxJob) -> tuple[OutboxJob, bool]: ...

    async def claim_publisher_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        allowed_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> tuple[OutboxJob, ...]: ...

    async def mark_published(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob: ...

    async def schedule_retry(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        error_code: str,
        now: datetime,
        expected_version: int,
        phase: str,
    ) -> OutboxJob: ...

    async def mark_dead_letter(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        error_code: str,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob: ...

    async def claim_for_processing(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        allowed_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> OutboxJob | None: ...

    async def mark_succeeded(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob: ...

    async def recover_expired_claims(self, *, now: datetime) -> tuple[OutboxJob, ...]: ...

    async def list_by_state(
        self,
        *,
        state: OutboxJobState,
        query_filter: OutboxReconciliationFilter,
    ) -> tuple[OutboxJob, ...]: ...

    async def renew_processor_claim(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob: ...

    async def requeue_dead_letter(self, *, job_id: UUID, now: datetime) -> OutboxJob: ...


class OutboxJobAttemptRepository(Protocol):
    async def append(self, attempt: OutboxJobAttempt) -> None: ...


class OutboxUnitOfWork(Protocol):
    outbox_jobs: OutboxJobRepository
    outbox_job_attempts: OutboxJobAttemptRepository

    async def __aenter__(self) -> OutboxUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
