"""Async worker CLI for outbox publication, processing, and reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import signal
from datetime import UTC, datetime, timedelta

from closeros_worker.runtime import VW_SUPPORTED_JOB_KINDS, WorkerRuntime, build_worker_runtime
from closeros_worker.settings import WorkerConfigurationError, WorkerSettings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CloserOS background worker")
    parser.add_argument(
        "mode",
        choices=("publisher", "processor", "reconcile-once", "reconcile-whatsapp-once", "all"),
        help="worker execution mode",
    )
    return parser


async def _run_publisher(runtime: WorkerRuntime, *, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        now = datetime.now(tz=UTC)
        uow = runtime.integrated_uow_factory()
        async with uow:
            publisher = runtime.publisher_service_factory()
            await publisher.publish_batch(
                now=now,
                batch_size=runtime.settings.publish_batch_size,
                allowed_job_kinds=VW_SUPPORTED_JOB_KINDS,
            )
            await uow.commit()
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=runtime.settings.polling_interval_seconds,
            )
        except TimeoutError:
            continue


async def _run_processor(runtime: WorkerRuntime, *, stop_event: asyncio.Event) -> None:
    await runtime.queue_consumer.ensure_group()
    while not stop_event.is_set():
        messages = await runtime.queue_consumer.read_job_ids()
        if not messages:
            continue

        now = datetime.now(tz=UTC)
        for message_id, job_id in messages:
            uow = runtime.integrated_uow_factory()
            async with uow:
                processor = runtime.processor_service_factory()
                await processor.process_job(job_id=job_id, now=now)
                await uow.commit()
            await runtime.queue_consumer.acknowledge(message_id=message_id)


async def _run_reconcile_once(runtime: WorkerRuntime) -> None:
    now = datetime.now(tz=UTC)
    overdue_before = now - timedelta(minutes=5)
    uow = runtime.integrated_uow_factory()
    async with uow:
        reconciliation = runtime.reconciliation_service_factory()
        await reconciliation.reconcile(now=now, overdue_before=overdue_before)
        await uow.commit()


async def _run_reconcile_whatsapp_once(runtime: WorkerRuntime) -> None:
    import os
    from uuid import UUID

    from closeros.application.audit_recording import AuditContext

    tenant_raw = os.environ.get("WHATSAPP_RECONCILE_TENANT_ID", "").strip()
    if not tenant_raw:
        raise WorkerConfigurationError("WHATSAPP_RECONCILE_TENANT_ID is not set")

    tenant_id = UUID(tenant_raw)
    reconciliation = runtime.whatsapp_reconciliation_service_factory()
    await reconciliation.reconcile_once(
        tenant_id=tenant_id,
        audit_context=AuditContext(correlation_id=tenant_id),
    )


async def _run_all(runtime: WorkerRuntime, *, stop_event: asyncio.Event) -> None:
    await asyncio.gather(
        _run_publisher(runtime, stop_event=stop_event),
        _run_processor(runtime, stop_event=stop_event),
    )


async def _async_main(mode: str) -> int:
    settings = WorkerSettings.from_env()
    runtime = build_worker_runtime(settings)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    try:
        if mode == "publisher":
            await _run_publisher(runtime, stop_event=stop_event)
        elif mode == "processor":
            await _run_processor(runtime, stop_event=stop_event)
        elif mode == "reconcile-once":
            await _run_reconcile_once(runtime)
        elif mode == "reconcile-whatsapp-once":
            await _run_reconcile_whatsapp_once(runtime)
        else:
            await _run_all(runtime, stop_event=stop_event)
    finally:
        await runtime.dispose()

    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_async_main(args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
