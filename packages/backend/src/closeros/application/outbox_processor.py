"""Application service for processing published transactional outbox jobs."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from closeros.application.clock import Clock, SystemClock
from closeros.application.outbox_persistence import (
    OutboxClaimMismatchError,
    OutboxJobAttemptRepository,
    OutboxJobRepository,
)
from closeros.domain.outbox import (
    PROCESSOR_LEASE_SECONDS,
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


class _FrozenClock:
    """Compatibility clock for callers that still pass a single ``now`` value."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


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
        clock: Clock | None = None,
    ) -> None:
        self._outbox_jobs = outbox_jobs
        self._outbox_job_attempts = outbox_job_attempts
        self._handlers = handlers
        self._worker_id = worker_id
        self._supported_job_kinds = supported_job_kinds
        self._injected_clock = clock

    def _resolve_clock(self, *, now: datetime | None) -> Clock:
        if self._injected_clock is not None:
            return self._injected_clock
        if now is not None:
            return _FrozenClock(now)
        return SystemClock()

    async def process_job(
        self,
        *,
        job_id: UUID,
        now: datetime | None = None,
    ) -> OutboxProcessorResult:
        """Process one published job.

        Lifecycle timestamps come from ``clock``. When no clock was injected,
        a caller-supplied ``now`` freezes all lifecycle points for compatibility.
        Inject an advancing clock to obtain non-zero attempt durations.
        """
        clock = self._resolve_clock(now=now)
        claim_at = clock.now()
        claimed = await self._outbox_jobs.claim_for_processing(
            job_id=job_id,
            worker_id=self._worker_id,
            now=claim_at,
            allowed_job_kinds=self._supported_job_kinds,
        )
        if claimed is None:
            return OutboxProcessorResult(job_id=job_id, outcome="not_claimed")

        started_at = clock.now()
        handler = self._handlers.get(claimed.job_kind)
        if handler is None:
            return await self._handle_failure(
                job=claimed,
                started_at=started_at,
                clock=clock,
                error_code=OutboxErrorCode.HANDLER_NOT_IMPLEMENTED,
            )

        renew_stop = asyncio.Event()
        current_job: list[OutboxJob] = [claimed]
        renew_task = asyncio.create_task(
            self._renew_processor_lease_loop(
                job_holder=current_job,
                stop_event=renew_stop,
                clock=clock,
            )
        )
        try:
            await handler.handle(job=claimed)
        except Exception as error:
            handler_error = _extract_typed_handler_error(error)
            active_job = current_job[0]
            if handler_error is not None:
                if handler_error.permanent:
                    return await self._handle_permanent_failure(
                        job=active_job,
                        started_at=started_at,
                        clock=clock,
                        error_code=handler_error.error_code,
                    )
                return await self._handle_failure(
                    job=active_job,
                    started_at=started_at,
                    clock=clock,
                    error_code=handler_error.error_code,
                )
            return await self._handle_failure(
                job=active_job,
                started_at=started_at,
                clock=clock,
                error_code=OutboxErrorCode.HANDLER_FAILED,
            )
        finally:
            renew_stop.set()
            renew_task.cancel()
            with suppress(asyncio.CancelledError):
                await renew_task

        active_job = current_job[0]
        finished_at = clock.now()
        try:
            updated = await self._outbox_jobs.mark_succeeded(
                job_id=active_job.id,
                claim_token=active_job.claim_token,  # type: ignore[arg-type]
                now=finished_at,
                expected_version=active_job.version,
            )
        except OutboxClaimMismatchError:
            await self._append_attempt(
                job=active_job,
                started_at=started_at,
                finished_at=finished_at,
                outcome=OutboxAttemptOutcome.FAILED,
                error_code=OutboxErrorCode.STALE_CLAIM,
            )
            return OutboxProcessorResult(job_id=job_id, outcome="stale_claim")

        await self._append_attempt(
            job=updated,
            started_at=started_at,
            finished_at=finished_at,
            outcome=OutboxAttemptOutcome.SUCCEEDED,
            error_code=None,
        )
        return OutboxProcessorResult(job_id=job_id, outcome="succeeded")

    async def _handle_permanent_failure(
        self,
        *,
        job: OutboxJob,
        started_at: datetime,
        clock: Clock,
        error_code: OutboxErrorCode,
    ) -> OutboxProcessorResult:
        finished_at = clock.now()
        await self._append_attempt(
            job=job,
            started_at=started_at,
            finished_at=finished_at,
            outcome=OutboxAttemptOutcome.FAILED,
            error_code=error_code,
        )
        try:
            await self._outbox_jobs.mark_dead_letter(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                error_code=error_code.value,
                now=finished_at,
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
        clock: Clock,
        error_code: OutboxErrorCode,
    ) -> OutboxProcessorResult:
        finished_at = clock.now()
        await self._append_attempt(
            job=job,
            started_at=started_at,
            finished_at=finished_at,
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
                    now=finished_at,
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
                now=finished_at,
                expected_version=job.version,
            )
        except OutboxTransitionError as error:
            raise OutboxProcessorError("outbox retry scheduling failed") from error

        try:
            await self._outbox_jobs.schedule_retry(
                job_id=job.id,
                claim_token=job.claim_token,  # type: ignore[arg-type]
                error_code=error_code.value,
                now=finished_at,
                expected_version=job.version,
                phase=OutboxJobPhase.PROCESSOR.value,
            )
        except OutboxClaimMismatchError as error:
            raise OutboxProcessorError("outbox retry persistence failed") from error
        return OutboxProcessorResult(job_id=job.id, outcome="retried")

    async def _renew_processor_lease_loop(
        self,
        *,
        job_holder: list[OutboxJob],
        stop_event: asyncio.Event,
        clock: Clock,
    ) -> None:
        interval_seconds = max(PROCESSOR_LEASE_SECONDS // 3, 10)
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                return
            except TimeoutError:
                pass

            current = job_holder[0]
            if current.claim_token is None:
                return

            try:
                job_holder[0] = await self._outbox_jobs.renew_processor_claim(
                    job_id=current.id,
                    claim_token=current.claim_token,
                    now=clock.now(),
                    expected_version=current.version,
                )
            except OutboxClaimMismatchError:
                return

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
    from closeros.application.crm_sync_handler import CrmSyncHandlerError
    from closeros.application.csv_import_processor import CsvImportHandlerError
    from closeros.application.knowledge_index_handler import KnowledgeIndexHandlerError
    from closeros.application.media_fetch_handler import MediaFetchHandlerError
    from closeros.application.media_scan_handler import MediaScanHandlerError
    from closeros.application.message_analyze_handler import MessageAnalyzeHandlerError
    from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandlerError
    from closeros.application.notification_deliver_handler import NotificationDeliverHandlerError
    from closeros.application.optional_feature_handler import OptionalFeatureDisabledHandlerError
    from closeros.application.provider_message_send_handler import ProviderMessageSendHandlerError
    from closeros.application.provider_templates_sync_handler import (
        ProviderTemplatesSyncHandlerError,
    )
    from closeros.application.retention_purge_handler import RetentionPurgeHandlerError
    from closeros.application.webhook_normalize_handler import WebhookNormalizeHandlerError

    if isinstance(
        error,
        (
            WebhookNormalizeHandlerError,
            CsvImportHandlerError,
            CrmSyncHandlerError,
            ContentRedactHandlerError,
            MetricsRecalculateHandlerError,
            KnowledgeIndexHandlerError,
            MessageAnalyzeHandlerError,
            NotificationDeliverHandlerError,
            MediaFetchHandlerError,
            MediaScanHandlerError,
            RetentionPurgeHandlerError,
            ProviderMessageSendHandlerError,
            ProviderTemplatesSyncHandlerError,
            OptionalFeatureDisabledHandlerError,
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
