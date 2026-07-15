"""Async worker CLI for outbox publication, processing, and reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.outbox_persistence import OutboxReconciliationFilter
from closeros.application.outbox_reconciliation import OutboxReconciliationService
from closeros.domain.encrypted_content import EncryptedContentKind
from closeros.domain.outbox import OutboxJobState

from closeros_worker.runtime import XY_SUPPORTED_JOB_KINDS, WorkerRuntime, build_worker_runtime
from closeros_worker.settings import WorkerConfigurationError, WorkerSettings

_CLI_MODES = (
    "publisher",
    "processor",
    "all",
    "reconcile-once",
    "reconcile-whatsapp-once",
    "reconcile-crm-once",
    "outbox-status",
    "dead-letter-list",
    "dead-letter-retry",
    "retention-run",
    "retention-status",
    "kms-rewrap-status",
    "kms-rewrap-run",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CloserOS background worker")
    parser.add_argument(
        "mode",
        choices=_CLI_MODES,
        help="worker execution mode",
    )
    return parser


def _print_safe_json(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True))


def _require_env_uuid(variable_name: str) -> UUID:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        raise WorkerConfigurationError(f"{variable_name} is not set")
    return UUID(raw_value)


def _parse_datetime_env(variable_name: str) -> datetime:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        raise WorkerConfigurationError(f"{variable_name} is not set")
    parsed = datetime.fromisoformat(raw_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


async def _run_publisher(runtime: WorkerRuntime, *, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        now = datetime.now(tz=UTC)
        uow = runtime.integrated_uow_factory()
        async with uow:
            publisher = runtime.publisher_service_factory(uow)
            await publisher.publish_batch(
                now=now,
                batch_size=runtime.settings.publish_batch_size,
                allowed_job_kinds=XY_SUPPORTED_JOB_KINDS,
            )
            await uow.commit()
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=runtime.settings.polling_interval_seconds,
            )
        except TimeoutError:
            continue


async def _process_message(
    runtime: WorkerRuntime,
    *,
    message_id: str,
    job_id: UUID,
    stop_event: asyncio.Event,
) -> None:
    if stop_event.is_set():
        return

    now = datetime.now(tz=UTC)
    uow = runtime.integrated_uow_factory()
    async with uow:
        processor = runtime.processor_service_factory(uow)
        await processor.process_job(job_id=job_id, now=now)
        await uow.commit()
    await runtime.queue_consumer.acknowledge(message_id=message_id)


async def _run_processor(runtime: WorkerRuntime, *, stop_event: asyncio.Event) -> None:
    await runtime.queue_consumer.ensure_group()
    semaphore = asyncio.Semaphore(runtime.settings.max_parallel_jobs)
    in_flight: set[asyncio.Task[None]] = set()

    async def _run_one(message_id: str, job_id: UUID) -> None:
        async with semaphore:
            await _process_message(
                runtime,
                message_id=message_id,
                job_id=job_id,
                stop_event=stop_event,
            )

    while not stop_event.is_set():
        messages = await runtime.queue_consumer.read_job_ids()
        if not messages:
            continue

        for message_id, job_id in messages:
            if stop_event.is_set():
                break
            task = asyncio.create_task(_run_one(message_id, job_id))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)

    if in_flight:
        try:
            await asyncio.wait_for(
                asyncio.gather(*in_flight, return_exceptions=True),
                timeout=runtime.settings.shutdown_grace_seconds,
            )
        except TimeoutError:
            for task in in_flight:
                task.cancel()


async def _run_reconcile_once(runtime: WorkerRuntime) -> None:
    now = datetime.now(tz=UTC)
    overdue_before = now - timedelta(minutes=5)
    uow = runtime.integrated_uow_factory()
    async with uow:
        reconciliation = runtime.reconciliation_service_factory(uow)
        report = await reconciliation.reconcile(now=now, overdue_before=overdue_before)
        await uow.commit()
    _print_safe_json(
        {
            "recovered_publisher_claims": report.recovered_publisher_claims,
            "recovered_processor_claims": report.recovered_processor_claims,
            "overdue_pending_jobs": report.overdue_pending_jobs,
            "dead_letter_jobs": report.dead_letter_jobs,
        }
    )


async def _run_reconcile_whatsapp_once(runtime: WorkerRuntime) -> None:
    tenant_id = _require_env_uuid("WHATSAPP_RECONCILE_TENANT_ID")
    reconciliation = runtime.whatsapp_reconciliation_service_factory()
    await reconciliation.reconcile_once(
        tenant_id=tenant_id,
        audit_context=AuditContext(correlation_id=tenant_id),
    )
    _print_safe_json({"status": "completed", "tenant_id": str(tenant_id)})


async def _run_reconcile_crm_once(runtime: WorkerRuntime) -> None:
    tenant_id = _require_env_uuid("CRM_RECONCILE_TENANT_ID")
    reconciliation = runtime.crm_reconciliation_service_factory()
    await reconciliation.reconcile_once(tenant_id=tenant_id)
    _print_safe_json({"status": "completed", "tenant_id": str(tenant_id)})


async def _run_outbox_status(runtime: WorkerRuntime) -> None:
    now = datetime.now(tz=UTC)
    overdue_before = now - timedelta(minutes=5)
    uow = runtime.integrated_uow_factory()
    async with uow:
        reconciliation = OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)
        report = await reconciliation.reconcile(now=now, overdue_before=overdue_before)
    _print_safe_json(
        {
            "recovered_publisher_claims": report.recovered_publisher_claims,
            "recovered_processor_claims": report.recovered_processor_claims,
            "overdue_pending_jobs": report.overdue_pending_jobs,
            "dead_letter_jobs": report.dead_letter_jobs,
        }
    )


async def _run_dead_letter_list(runtime: WorkerRuntime) -> None:
    limit = int(os.environ.get("DEAD_LETTER_LIST_LIMIT", "50"))
    uow = runtime.integrated_uow_factory()
    async with uow:
        jobs = await uow.outbox_jobs.list_by_state(
            state=OutboxJobState.DEAD_LETTER,
            query_filter=OutboxReconciliationFilter(limit=limit),
        )
    _print_safe_json(
        {
            "jobs": [
                {
                    "job_id": str(job.id),
                    "tenant_id": None if job.tenant_id is None else str(job.tenant_id),
                    "job_kind": job.job_kind.value,
                    "last_error_code": None
                    if job.last_error_code is None
                    else job.last_error_code.value,
                }
                for job in jobs
            ]
        }
    )


async def _run_dead_letter_retry(runtime: WorkerRuntime) -> None:
    if os.environ.get("DEAD_LETTER_RETRY_ALLOWED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise WorkerConfigurationError("DEAD_LETTER_RETRY_ALLOWED must be true")

    job_id = _require_env_uuid("DEAD_LETTER_RETRY_JOB_ID")
    now = datetime.now(tz=UTC)
    uow = runtime.integrated_uow_factory()
    async with uow:
        updated = await uow.outbox_jobs.requeue_dead_letter(job_id=job_id, now=now)
        await uow.commit()
    _print_safe_json(
        {
            "job_id": str(updated.id),
            "state": updated.state.value,
            "status": "requeued",
        }
    )


async def _run_retention_run(runtime: WorkerRuntime) -> None:
    tenant_id = _require_env_uuid("RETENTION_TENANT_ID")
    expires_before = _parse_datetime_env("RETENTION_EXPIRES_BEFORE")
    service = runtime.retention_purge_service_factory()
    purge_run_id = await service.schedule_purge(
        tenant_id=tenant_id,
        expires_before=expires_before,
        requested_at=datetime.now(tz=UTC),
    )
    _print_safe_json(
        {
            "purge_run_id": str(purge_run_id),
            "tenant_id": str(tenant_id),
            "status": "scheduled",
        }
    )


async def _run_retention_status(runtime: WorkerRuntime) -> None:
    tenant_id = _require_env_uuid("RETENTION_TENANT_ID")
    purge_run_id = _require_env_uuid("RETENTION_PURGE_RUN_ID")
    service = runtime.retention_purge_service_factory()
    purge_run = await service.get_purge_run(tenant_id=tenant_id, purge_run_id=purge_run_id)
    if purge_run is None:
        _print_safe_json({"status": "not_found", "purge_run_id": str(purge_run_id)})
        return
    _print_safe_json(
        {
            "purge_run_id": str(purge_run.id),
            "tenant_id": str(purge_run.tenant_id),
            "status": purge_run.status.value,
            "dry_run": purge_run.dry_run,
            "items_scanned": purge_run.items_scanned,
            "items_deleted": purge_run.items_deleted,
            "items_skipped_legal_hold": purge_run.items_skipped_legal_hold,
        }
    )


async def _run_kms_rewrap_status(runtime: WorkerRuntime) -> None:
    expires_before_raw = os.environ.get("KMS_REWRAP_EXPIRES_BEFORE", "").strip()
    expires_before = (
        _parse_datetime_env("KMS_REWRAP_EXPIRES_BEFORE")
        if expires_before_raw
        else datetime.now(tz=UTC)
    )
    service = runtime.kms_rewrap_service_factory()
    due_count = await service.count_due_for_retention(expires_before=expires_before)
    _print_safe_json({"due_count": due_count, "expires_before": expires_before.isoformat()})


async def _run_kms_rewrap_run(runtime: WorkerRuntime) -> None:
    tenant_id = _require_env_uuid("KMS_REWRAP_TENANT_ID")
    kind_raw = os.environ.get("KMS_REWRAP_CONTENT_KIND", "message_body").strip()
    kind = EncryptedContentKind(kind_raw)
    correlation_id = _require_env_uuid("KMS_REWRAP_CORRELATION_ID")
    service = runtime.kms_rewrap_service_factory()
    rewrapped = await service.rewrap_tenant_contents(
        tenant_id=tenant_id,
        kind=kind,
        occurred_at=datetime.now(tz=UTC),
        correlation_id=correlation_id,
    )
    _print_safe_json(
        {
            "tenant_id": str(tenant_id),
            "content_kind": kind.value,
            "rewrapped_count": rewrapped,
            "status": "completed",
        }
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
        elif mode == "reconcile-crm-once":
            await _run_reconcile_crm_once(runtime)
        elif mode == "outbox-status":
            await _run_outbox_status(runtime)
        elif mode == "dead-letter-list":
            await _run_dead_letter_list(runtime)
        elif mode == "dead-letter-retry":
            await _run_dead_letter_retry(runtime)
        elif mode == "retention-run":
            await _run_retention_run(runtime)
        elif mode == "retention-status":
            await _run_retention_status(runtime)
        elif mode == "kms-rewrap-status":
            await _run_kms_rewrap_status(runtime)
        elif mode == "kms-rewrap-run":
            await _run_kms_rewrap_run(runtime)
        else:
            await _run_all(runtime, stop_event=stop_event)
    finally:
        await runtime.dispose()

    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_async_main(args.mode))
    except WorkerConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
