"""Application service for outbox reconciliation and expired-claim recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from closeros.application.outbox_persistence import (
    OutboxJobRepository,
    OutboxReconciliationFilter,
)
from closeros.domain.outbox import OutboxJobState


@dataclass(frozen=True, slots=True)
class OutboxReconciliationReport:
    recovered_publisher_claims: int
    recovered_processor_claims: int
    overdue_pending_jobs: int
    dead_letter_jobs: int


class OutboxReconciliationService:
    """Recovers expired claims and reports bounded metadata-only counts."""

    def __init__(self, *, outbox_jobs: OutboxJobRepository) -> None:
        self._outbox_jobs = outbox_jobs

    async def reconcile(
        self,
        *,
        now: datetime,
        overdue_before: datetime,
        limit: int = 100,
    ) -> OutboxReconciliationReport:
        recovered = await self._outbox_jobs.recover_expired_claims(now=now)
        recovered_publisher_claims = sum(
            1 for job in recovered if job.state is OutboxJobState.PENDING
        )
        recovered_processor_claims = sum(
            1 for job in recovered if job.state is OutboxJobState.PUBLISHED
        )

        overdue_pending = await self._outbox_jobs.list_by_state(
            state=OutboxJobState.PENDING,
            query_filter=OutboxReconciliationFilter(
                overdue_before=overdue_before,
                limit=limit,
            ),
        )
        dead_letter_jobs = await self._outbox_jobs.list_by_state(
            state=OutboxJobState.DEAD_LETTER,
            query_filter=OutboxReconciliationFilter(limit=limit),
        )

        return OutboxReconciliationReport(
            recovered_publisher_claims=recovered_publisher_claims,
            recovered_processor_claims=recovered_processor_claims,
            overdue_pending_jobs=len(overdue_pending),
            dead_letter_jobs=len(dead_letter_jobs),
        )
