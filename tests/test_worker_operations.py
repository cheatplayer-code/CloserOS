"""Tests for worker operational behavior."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from closeros.application.outbox_processor import OutboxProcessorService
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    OutboxJobState,
    build_outbox_job,
)
from closeros_worker import __main__ as worker_main
from closeros_worker.settings import WorkerConfigurationError, WorkerSettings

# Synthetic userinfo kept split from the scheme so no complete credentialed URI
# literal is committed to source.
_SYNTHETIC_USERINFO = "user:secret"


def _worker_settings(**overrides: object) -> WorkerSettings:
    base = {
        "app_env": "development",
        "database_url": f"postgresql://{_SYNTHETIC_USERINFO}@127.0.0.1:5432/closeros_local",
        "redis_url": "redis://127.0.0.1:6379/0",
        "outbox_stream": "closeros.outbox.jobs",
        "outbox_consumer_group": "closeros.outbox.processors",
        "worker_id": "worker-test",
        "polling_interval_seconds": 1.0,
        "publish_batch_size": 25,
        "processor_block_ms": 5_000,
        "max_parallel_jobs": 2,
        "shutdown_grace_seconds": 1.0,
    }
    base.update(overrides)
    return WorkerSettings(**base)  # type: ignore[arg-type]


def test_worker_settings_include_concurrency_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_MAX_PARALLEL_JOBS", "7")
    monkeypatch.setenv("WORKER_SHUTDOWN_GRACE_SECONDS", "45")
    settings = WorkerSettings.from_env()
    assert settings.max_parallel_jobs == 7
    assert settings.shutdown_grace_seconds == 45.0


def test_processor_respects_max_parallel_jobs() -> None:
    async def exercise() -> None:
        settings = _worker_settings(max_parallel_jobs=2)
        runtime = MagicMock()
        runtime.settings = settings
        runtime.queue_consumer.ensure_group = AsyncMock()

        read_calls = 0

        async def read_job_ids() -> list[tuple[str, object]]:
            nonlocal read_calls
            read_calls += 1
            if read_calls == 1:
                return [
                    ("1-0", uuid4()),
                    ("1-1", uuid4()),
                    ("1-2", uuid4()),
                ]
            await asyncio.sleep(0.2)
            return []

        runtime.queue_consumer.read_job_ids = AsyncMock(side_effect=read_job_ids)
        runtime.queue_consumer.acknowledge = AsyncMock()
        runtime.integrated_uow_factory = MagicMock()
        uow = AsyncMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=False)
        uow.commit = AsyncMock()
        runtime.integrated_uow_factory.return_value = uow

        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def tracked_process(**_: object) -> None:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1

        processor = MagicMock()
        processor.process_job = AsyncMock(side_effect=tracked_process)
        runtime.processor_service_factory = MagicMock(return_value=processor)

        stop_event = asyncio.Event()

        async def stop_soon() -> None:
            await asyncio.sleep(0.25)
            stop_event.set()

        await asyncio.gather(
            worker_main._run_processor(runtime, stop_event=stop_event),
            stop_soon(),
        )
        assert peak <= settings.max_parallel_jobs

    asyncio.run(exercise())


def test_processor_stops_accepting_after_shutdown_signal() -> None:
    async def exercise() -> None:
        settings = _worker_settings(max_parallel_jobs=4)
        runtime = MagicMock()
        runtime.settings = settings
        runtime.queue_consumer.ensure_group = AsyncMock()
        job_id = uuid4()
        runtime.queue_consumer.read_job_ids = AsyncMock(
            return_value=[("1-0", job_id), ("1-1", uuid4())]
        )
        runtime.queue_consumer.acknowledge = AsyncMock()
        runtime.integrated_uow_factory = MagicMock()
        uow = AsyncMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=False)
        uow.commit = AsyncMock()
        runtime.integrated_uow_factory.return_value = uow
        processor = MagicMock()
        processor.process_job = AsyncMock()
        runtime.processor_service_factory = MagicMock(return_value=processor)

        stop_event = asyncio.Event()
        stop_event.set()
        await worker_main._run_processor(runtime, stop_event=stop_event)
        processor.process_job.assert_not_called()
        runtime.queue_consumer.acknowledge.assert_not_called()

    asyncio.run(exercise())


def test_unsupported_job_kind_is_classified() -> None:
    async def exercise() -> None:
        outbox_jobs = AsyncMock()
        outbox_job_attempts = AsyncMock()
        tenant_id = uuid4()
        job = build_outbox_job(
            job_id=uuid4(),
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.WEBHOOK_NORMALIZE,
            reference=OutboxJobReference(
                resource_type="webhook_event",
                resource_id=uuid4(),
                schema_version=1,
                tenant_id=tenant_id,
            ),
            deduplication_key=f"unsupported-{uuid.uuid4()}",
            created_at=datetime.now(tz=UTC),
        )
        now = datetime.now(tz=UTC)
        claimed = replace(
            job,
            state=OutboxJobState.PROCESSING,
            claim_token=uuid4(),
            claimed_by="worker-test",
            claimed_at=now,
            claim_expires_at=now + timedelta(minutes=5),
        )
        outbox_jobs.claim_for_processing = AsyncMock(return_value=claimed)
        outbox_jobs.renew_processor_claim = AsyncMock(return_value=claimed)
        outbox_jobs.schedule_retry = AsyncMock(return_value=claimed)
        outbox_job_attempts.append = AsyncMock()

        processor = OutboxProcessorService(
            outbox_jobs=outbox_jobs,
            outbox_job_attempts=outbox_job_attempts,
            handlers={},
            worker_id="worker-test",
        )
        result = await processor.process_job(job_id=job.id, now=now)
        assert result.outcome == "retried"

    asyncio.run(exercise())


def test_dead_letter_retry_requires_explicit_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock()
    monkeypatch.delenv("DEAD_LETTER_RETRY_ALLOWED", raising=False)
    with pytest.raises(WorkerConfigurationError, match="DEAD_LETTER_RETRY_ALLOWED"):
        asyncio.run(worker_main._run_dead_letter_retry(runtime))


def test_cli_includes_operational_modes() -> None:
    assert "outbox-status" in worker_main._CLI_MODES
    assert "dead-letter-list" in worker_main._CLI_MODES
    assert "dead-letter-retry" in worker_main._CLI_MODES
    assert "retention-run" in worker_main._CLI_MODES
    assert "kms-rewrap-run" in worker_main._CLI_MODES
