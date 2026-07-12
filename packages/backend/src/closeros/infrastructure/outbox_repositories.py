"""PostgreSQL repository implementations for transactional outbox persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.outbox_persistence import (
    DuplicateOutboxJobError,
    OutboxClaimMismatchError,
    OutboxPersistenceError,
    OutboxReconciliationFilter,
    OutboxRecordNotFoundError,
    OutboxStaleVersionError,
)
from closeros.domain.outbox import (
    OutboxClaimError,
    OutboxErrorCode,
    OutboxJob,
    OutboxJobAttempt,
    OutboxJobKind,
    OutboxJobPhase,
    OutboxJobState,
    OutboxTransitionError,
    claim_for_processing,
    claim_for_publishing,
    mark_dead_letter,
    mark_published,
    mark_succeeded,
    recover_expired_processor_claim,
    recover_expired_publisher_claim,
    schedule_retry,
)
from closeros.infrastructure import outbox_mappers as mappers
from closeros.infrastructure.outbox_orm import OutboxJobRow
from closeros.infrastructure.persistence_errors import translate_integrity_error

_CONSTRAINT_ERRORS: dict[str, type[OutboxPersistenceError]] = {
    "uq_outbox_jobs_tenant_id_deduplication_key": DuplicateOutboxJobError,
    "uq_outbox_jobs_global_deduplication_key": DuplicateOutboxJobError,
}


def _translate_integrity_error(error: IntegrityError) -> OutboxPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=OutboxPersistenceError,
        message="outbox persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


def _map_domain_claim_error(error: OutboxClaimError) -> OutboxClaimMismatchError:
    return OutboxClaimMismatchError("outbox claim validation failed")


def _map_domain_transition_error(
    error: OutboxClaimError | OutboxTransitionError,
) -> OutboxClaimMismatchError:
    return OutboxClaimMismatchError("outbox transition validation failed")


async def _get_job_row_required(
    session: AsyncSession,
    *,
    job_id: UUID,
) -> OutboxJobRow:
    row = await session.get(OutboxJobRow, job_id)
    if row is None:
        raise OutboxRecordNotFoundError("outbox job not found")
    return row


class SqlAlchemyOutboxJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, job: OutboxJob) -> None:
        self._session.add(mappers.outbox_job_to_row(job))
        await _flush(self._session)

    async def get_by_id(self, *, job_id: UUID) -> OutboxJob | None:
        row = await self._session.get(OutboxJobRow, job_id)
        return None if row is None else mappers.outbox_job_to_domain(row)

    async def get_or_create(self, job: OutboxJob) -> tuple[OutboxJob, bool]:
        existing = await self._find_by_deduplication_key(
            tenant_id=job.tenant_id,
            deduplication_key=job.deduplication_key,
        )
        if existing is not None:
            return existing, False
        try:
            await self.enqueue(job)
        except DuplicateOutboxJobError:
            existing = await self._find_by_deduplication_key(
                tenant_id=job.tenant_id,
                deduplication_key=job.deduplication_key,
            )
            if existing is None:
                raise
            return existing, False
        return job, True

    async def _find_by_deduplication_key(
        self,
        *,
        tenant_id: UUID | None,
        deduplication_key: str,
    ) -> OutboxJob | None:
        statement = select(OutboxJobRow).where(
            OutboxJobRow.deduplication_key == deduplication_key,
        )
        if tenant_id is None:
            statement = statement.where(OutboxJobRow.tenant_id.is_(None))
        else:
            statement = statement.where(OutboxJobRow.tenant_id == tenant_id)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.outbox_job_to_domain(row)

    async def claim_publisher_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        allowed_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> tuple[OutboxJob, ...]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        statement = (
            select(OutboxJobRow)
            .where(
                OutboxJobRow.state.in_(
                    (
                        OutboxJobState.PENDING.value,
                        OutboxJobState.RETRY_SCHEDULED.value,
                    )
                ),
                OutboxJobRow.available_at <= now,
            )
            .order_by(
                OutboxJobRow.priority.asc(),
                OutboxJobRow.available_at.asc(),
                OutboxJobRow.created_at.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        if allowed_job_kinds is not None:
            statement = statement.where(
                OutboxJobRow.job_kind.in_(tuple(kind.value for kind in allowed_job_kinds))
            )
        rows = (await self._session.execute(statement)).scalars().all()
        claimed_jobs: list[OutboxJob] = []
        for row in rows:
            current = mappers.outbox_job_to_domain(row)
            claim_token = uuid4()
            try:
                updated = claim_for_publishing(
                    current,
                    claim_token=claim_token,
                    worker_id=worker_id,
                    now=now,
                    expected_version=current.version,
                )
            except (OutboxClaimError, OutboxTransitionError) as error:
                raise _map_domain_transition_error(error) from error
            mappers.update_outbox_job_row(row, updated)
            claimed_jobs.append(updated)
        if claimed_jobs:
            await _flush(self._session)
        return tuple(claimed_jobs)

    async def mark_published(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob:
        row = await _get_job_row_required(self._session, job_id=job_id)
        current = mappers.outbox_job_to_domain(row)
        try:
            updated = mark_published(
                current,
                claim_token=claim_token,
                now=now,
                expected_version=expected_version,
            )
        except OutboxClaimError as error:
            raise _map_domain_claim_error(error) from error
        except OutboxTransitionError as error:
            raise _map_domain_transition_error(error) from error
        if row.version != expected_version:
            raise OutboxStaleVersionError("outbox job version mismatch")
        mappers.update_outbox_job_row(row, updated)
        await _flush(self._session)
        return updated

    async def schedule_retry(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        error_code: str,
        now: datetime,
        expected_version: int,
        phase: str,
    ) -> OutboxJob:
        row = await _get_job_row_required(self._session, job_id=job_id)
        current = mappers.outbox_job_to_domain(row)
        resolved_phase = OutboxJobPhase(phase)
        resolved_error = OutboxErrorCode(error_code)
        try:
            updated = schedule_retry(
                current,
                claim_token=claim_token,
                phase=resolved_phase,
                error_code=resolved_error,
                now=now,
                expected_version=expected_version,
            )
        except OutboxClaimError as error:
            raise _map_domain_claim_error(error) from error
        except OutboxTransitionError as error:
            raise _map_domain_transition_error(error) from error
        if row.version != expected_version:
            raise OutboxStaleVersionError("outbox job version mismatch")
        mappers.update_outbox_job_row(row, updated)
        await _flush(self._session)
        return updated

    async def mark_dead_letter(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        error_code: str,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob:
        row = await _get_job_row_required(self._session, job_id=job_id)
        current = mappers.outbox_job_to_domain(row)
        resolved_error = OutboxErrorCode(error_code)
        try:
            updated = mark_dead_letter(
                current,
                claim_token=claim_token,
                error_code=resolved_error,
                now=now,
                expected_version=expected_version,
            )
        except OutboxClaimError as error:
            raise _map_domain_claim_error(error) from error
        except OutboxTransitionError as error:
            raise _map_domain_transition_error(error) from error
        if row.version != expected_version:
            raise OutboxStaleVersionError("outbox job version mismatch")
        mappers.update_outbox_job_row(row, updated)
        await _flush(self._session)
        return updated

    async def claim_for_processing(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        allowed_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> OutboxJob | None:
        statement = (
            select(OutboxJobRow)
            .where(
                OutboxJobRow.id == job_id,
                OutboxJobRow.state == OutboxJobState.PUBLISHED.value,
                OutboxJobRow.available_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        if allowed_job_kinds is not None:
            statement = statement.where(
                OutboxJobRow.job_kind.in_(tuple(kind.value for kind in allowed_job_kinds))
            )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        current = mappers.outbox_job_to_domain(row)
        claim_token = uuid4()
        try:
            updated = claim_for_processing(
                current,
                claim_token=claim_token,
                worker_id=worker_id,
                now=now,
                expected_version=current.version,
            )
        except (OutboxClaimError, OutboxTransitionError) as error:
            raise _map_domain_transition_error(error) from error
        mappers.update_outbox_job_row(row, updated)
        await _flush(self._session)
        return updated

    async def mark_succeeded(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        now: datetime,
        expected_version: int,
    ) -> OutboxJob:
        row = await _get_job_row_required(self._session, job_id=job_id)
        current = mappers.outbox_job_to_domain(row)
        try:
            updated = mark_succeeded(
                current,
                claim_token=claim_token,
                now=now,
                expected_version=expected_version,
            )
        except OutboxClaimError as error:
            raise _map_domain_claim_error(error) from error
        except OutboxTransitionError as error:
            raise _map_domain_transition_error(error) from error
        if row.version != expected_version:
            raise OutboxStaleVersionError("outbox job version mismatch")
        mappers.update_outbox_job_row(row, updated)
        await _flush(self._session)
        return updated

    async def recover_expired_claims(self, *, now: datetime) -> tuple[OutboxJob, ...]:
        statement = (
            select(OutboxJobRow)
            .where(
                OutboxJobRow.claim_expires_at.is_not(None),
                OutboxJobRow.claim_expires_at <= now,
                OutboxJobRow.state.in_(
                    (
                        OutboxJobState.PUBLISHING.value,
                        OutboxJobState.PROCESSING.value,
                    )
                ),
            )
            .with_for_update(skip_locked=True)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        recovered: list[OutboxJob] = []
        for row in rows:
            current = mappers.outbox_job_to_domain(row)
            try:
                if current.state is OutboxJobState.PUBLISHING:
                    updated = recover_expired_publisher_claim(current, now=now)
                else:
                    updated = recover_expired_processor_claim(current, now=now)
            except OutboxTransitionError:
                continue
            mappers.update_outbox_job_row(row, updated)
            recovered.append(updated)
        if recovered:
            await _flush(self._session)
        return tuple(recovered)

    async def list_by_state(
        self,
        *,
        state: OutboxJobState,
        query_filter: OutboxReconciliationFilter,
    ) -> tuple[OutboxJob, ...]:
        if query_filter.limit < 1:
            raise ValueError("limit must be positive")

        statement = select(OutboxJobRow).where(OutboxJobRow.state == state.value)
        if query_filter.tenant_id is not None:
            statement = statement.where(OutboxJobRow.tenant_id == query_filter.tenant_id)
        if query_filter.overdue_before is not None:
            statement = statement.where(OutboxJobRow.available_at <= query_filter.overdue_before)
        statement = statement.order_by(
            OutboxJobRow.available_at.asc(),
            OutboxJobRow.created_at.asc(),
        ).limit(query_filter.limit)
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.outbox_job_to_domain(row) for row in rows)


class SqlAlchemyOutboxJobAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, attempt: OutboxJobAttempt) -> None:
        self._session.add(mappers.outbox_job_attempt_to_row(attempt))
        await _flush(self._session)
