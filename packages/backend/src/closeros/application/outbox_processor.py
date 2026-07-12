"""Application service for processing published transactional outbox jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from closeros.application.outbox_persistence import (
    OutboxClaimMismatchError,
    OutboxJobAttemptRepository,
    OutboxJobRepository,
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


class OutboxJobHandler(Protocol):
    async def handle(self, *, job: OutboxJob) -> None: ...


class OutboxProcessorError(Exception):
    """Base class for safe outbox processor failures."""


@dataclass(frozen=True, slots=True)
class OutboxProcessorResult:
    job_id: UUID
    outcome: str


class NoOpOutboxJobHandler:
    """Test/no-op handler that acknowledges supported job kinds without side effects."""

    _SUPPORTED_KINDS: frozenset[OutboxJobKind] = frozenset(OutboxJobKind)

    async def handle(self, *, job: OutboxJob) -> None:
        if job.job_kind not in self._SUPPORTED_KINDS:
            raise OutboxProcessorError("unsupported outbox job kind")


class OutboxProcessorService:
    """Claims published jobs and dispatches them to injected handlers by kind."""

    def __init__(
        self,
        *,
        outbox_jobs: OutboxJobRepository,
        outbox_job_attempts: OutboxJobAttemptRepository,
        handlers: dict[OutboxJobKind, OutboxJobHandler],
        worker_id: str,
        supported_job_kinds: frozenset[OutboxJobKind] | None = None,
    ) -> None:
        self._outbox_jobs = outbox_jobs
        self._outbox_job_attempts = outbox_job_attempts
        self._handlers = handlers
        self._worker_id = worker_id
        self._supported_job_kinds = supported_job_kinds

    async def process_job(self, *, job_id: UUID, now: datetime) -> OutboxProcessorResult:
        claimed = await self._outbox_jobs.claim_for_processing(
            job_id=job_id,
            worker_id=self._worker_id,
            now=now,
            allowed_job_kinds=self._supported_job_kinds,
        )
        if claimed is None:
            return OutboxProcessorResult(job_id=job_id, outcome="not_claimed")

        started_at = now
        handler = self._handlers.get(claimed.job_kind)
        if handler is None:
            return await self._handle_failure(
                job=claimed,
                started_at=started_at,
                now=now,
                error_code=OutboxErrorCode.HANDLER_NOT_IMPLEMENTED,
            )

        try:
            await handler.handle(job=claimed)
        except Exception as error:
            handler_error = _extract_typed_handler_error(error)
            if handler_error is not None:
                if handler_error.permanent:
                    return await self._handle_permanent_failure(
                        job=claimed,
                        started_at=started_at,
                        now=now,
                        error_code=handler_error.error_code,
                    )
                return await self._handle_failure(
                    job=claimed,
                    started_at=started_at,
                    now=now,
                    error_code=handler_error.error_code,
                )
            return await self._handle_failure(
                job=claimed,
                started_at=started_at,
                now=now,
                error_code=OutboxErrorCode.HANDLER_FAILED,
            )

        try:
            updated = await self._outbox_jobs.mark_succeeded(
                job_id=claimed.id,
                claim_token=claimed.claim_token,  # type: ignore[arg-type]
                now=now,
                expected_version=claimed.version,
            )
        except OutboxClaimMismatchError:
            await self._append_attempt(
                job=claimed,
                started_at=started_at,
                finished_at=now,
                outcome=OutboxAttemptOutcome.FAILED,
                error_code=OutboxErrorCode.STALE_CLAIM,
            )
            return OutboxProcessorResult(job_id=job_id, outcome="stale_claim")

        await self._append_attempt(
            job=updated,
            started_at=started_at,
            finished_at=now,
            outcome=OutboxAttemptOutcome.SUCCEEDED,
            error_code=None,
        )
        return OutboxProcessorResult(job_id=job_id, outcome="succeeded")

    async def _handle_permanent_failure(
        self,
        *,
        job: OutboxJob,
        started_at: datetime,
        now: datetime,
        error_code: OutboxErrorCode,
    ) -> OutboxProcessorResult:
        await self._append_attempt(
            job=job,
            started_at=started_at,
            finished_at=now,
            outcome=OutboxAttemptOutcome.FAILED,
            error_code=error_code,
        )
        try:
            await self._outbox_jobs.mark_dead_letter(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                error_code=error_code.value,
                now=now,
                expected_version=job.version,
            )
        except OutboxClaimMismatchError as error:
            raise OutboxProcessorError("outbox dead-letter finalization failed") from error
        return OutboxProcessorResult(job_id=job.id, outcome="dead_lettered")

    async def _handle_failure(
        self,
        *,
        job: OutboxJob,
        started_at: datetime,
        now: datetime,
        error_code: OutboxErrorCode,
    ) -> OutboxProcessorResult:
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
                raise OutboxProcessorError("outbox dead-letter finalization failed") from error
            return OutboxProcessorResult(job_id=job.id, outcome="dead_lettered")

        try:
            schedule_retry(
                job,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                phase=OutboxJobPhase.PROCESSOR,
                error_code=error_code,
                now=now,
                expected_version=job.version,
            )
        except OutboxTransitionError as error:
            raise OutboxProcessorError("outbox retry scheduling failed") from error

        try:
            await self._outbox_jobs.schedule_retry(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                error_code=error_code.value,
                now=now,
                expected_version=job.version,
                phase=OutboxJobPhase.PROCESSOR.value,
            )
        except OutboxClaimMismatchError as error:
            raise OutboxProcessorError("outbox retry persistence failed") from error
        return OutboxProcessorResult(job_id=job.id, outcome="retried")

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
            phase=OutboxJobPhase.PROCESSOR,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            claim_token=job.claim_token or uuid4(),
            error_code=error_code,
        )
        await self._outbox_job_attempts.append(attempt)


def _extract_typed_handler_error(
    error: Exception,
) -> _TypedHandlerFailure | None:
    from closeros.application.content_redact_handler import ContentRedactHandlerError
    from closeros.application.csv_import_processor import CsvImportHandlerError
    from closeros.application.knowledge_index_handler import KnowledgeIndexHandlerError
    from closeros.application.message_analyze_handler import MessageAnalyzeHandlerError
    from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandlerError
    from closeros.application.webhook_normalize_handler import WebhookNormalizeHandlerError

    if isinstance(
        error,
        (
            WebhookNormalizeHandlerError,
            CsvImportHandlerError,
            ContentRedactHandlerError,
            MetricsRecalculateHandlerError,
            KnowledgeIndexHandlerError,
            MessageAnalyzeHandlerError,
        ),
    ):
        return _TypedHandlerFailure(
            error_code=error.error_code,
            permanent=error.permanent,
        )
    return None


@dataclass(frozen=True, slots=True)
class _TypedHandlerFailure:
    error_code: OutboxErrorCode
    permanent: bool


def build_noop_handlers() -> dict[OutboxJobKind, OutboxJobHandler]:
    handler = NoOpOutboxJobHandler()
    return {kind: handler for kind in OutboxJobKind}
