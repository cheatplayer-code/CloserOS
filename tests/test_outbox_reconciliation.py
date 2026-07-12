"""Integration tests for outbox reconciliation service."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from closeros.application.outbox_reconciliation import OutboxReconciliationService
from closeros.domain.outbox import (
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)

from tests.encryption_support import NOW, OUTBOX_JOB_B_ID, OUTBOX_JOB_ID

pytestmark = pytest.mark.hi_persistence

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000100")


async def _enqueue(integrated_uow_factory: Any, job: object) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.outbox_jobs.enqueue(job)
        await uow.commit()


def test_reconciliation_recovers_expired_publisher_claim(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        expired_now = NOW - timedelta(hours=2)
        job = build_outbox_job(
            job_id=OUTBOX_JOB_ID,
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A,
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_reconcile",
            created_at=expired_now,
            available_at=expired_now,
        )
        await _enqueue(integrated_uow_factory, job)
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=expired_now,
                batch_size=1,
            )
            assert len(claimed) == 1
            await uow.commit()
        reconcile_uow = integrated_uow_factory()
        async with reconcile_uow:
            service = OutboxReconciliationService(outbox_jobs=reconcile_uow.outbox_jobs)
            report = await service.reconcile(
                now=NOW,
                overdue_before=NOW + timedelta(minutes=5),
                limit=10,
            )
            await reconcile_uow.commit()
        assert report.recovered_publisher_claims == 1
        assert report.recovered_processor_claims == 0

    asyncio.run(exercise())


def test_reconciliation_recovers_expired_processor_claim(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        expired_now = NOW - timedelta(hours=2)
        job = build_outbox_job(
            job_id=OUTBOX_JOB_ID,
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A,
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_reconcile_processor",
            created_at=expired_now,
            available_at=expired_now,
        )
        await _enqueue(integrated_uow_factory, job)
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=expired_now,
                batch_size=1,
            )
            publishing = claimed[0]
            await uow.outbox_jobs.mark_published(
                job_id=publishing.id,
                claim_token=publishing.claim_token,
                now=expired_now,
                expected_version=publishing.version,
            )
            await uow.outbox_jobs.claim_for_processing(
                job_id=publishing.id,
                worker_id="processor-a",
                now=expired_now,
            )
            await uow.commit()
        reconcile_uow = integrated_uow_factory()
        async with reconcile_uow:
            service = OutboxReconciliationService(outbox_jobs=reconcile_uow.outbox_jobs)
            report = await service.reconcile(
                now=NOW,
                overdue_before=NOW + timedelta(minutes=5),
                limit=10,
            )
            await reconcile_uow.commit()
        assert report.recovered_processor_claims == 1

    asyncio.run(exercise())


def test_reconciliation_counts_overdue_pending_jobs(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        overdue_job = build_outbox_job(
            job_id=OUTBOX_JOB_ID,
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A,
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_overdue",
            created_at=NOW - timedelta(hours=3),
            available_at=NOW - timedelta(hours=2),
        )
        await _enqueue(integrated_uow_factory, overdue_job)
        uow = integrated_uow_factory()
        async with uow:
            service = OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)
            report = await service.reconcile(
                now=NOW,
                overdue_before=NOW - timedelta(minutes=30),
                limit=10,
            )
        assert report.overdue_pending_jobs == 1

    asyncio.run(exercise())


def test_reconciliation_counts_dead_letter_jobs(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        job = build_outbox_job(
            job_id=OUTBOX_JOB_ID,
            tenant_id=TENANT_A,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            reference=OutboxJobReference(
                tenant_id=TENANT_A,
                resource_type="message",
                resource_id=RESOURCE_ID,
                schema_version=1,
            ),
            deduplication_key="content_redact_dead",
            created_at=NOW,
            max_attempts=1,
        )
        await _enqueue(integrated_uow_factory, job)
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.outbox_jobs.claim_publisher_batch(
                worker_id="publisher-a",
                now=NOW,
                batch_size=1,
            )
            publishing = claimed[0]
            await uow.outbox_jobs.mark_dead_letter(
                job_id=publishing.id,
                claim_token=publishing.claim_token,
                error_code="max_attempts_exceeded",
                now=NOW,
                expected_version=publishing.version,
            )
            await uow.commit()
        reconcile_uow = integrated_uow_factory()
        async with reconcile_uow:
            service = OutboxReconciliationService(outbox_jobs=reconcile_uow.outbox_jobs)
            report = await service.reconcile(
                now=NOW,
                overdue_before=NOW + timedelta(minutes=5),
                limit=10,
            )
        assert report.dead_letter_jobs == 1

    asyncio.run(exercise())


def test_reconciliation_report_is_metadata_only(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = integrated_uow_factory()
        async with uow:
            service = OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)
            report = await service.reconcile(
                now=NOW,
                overdue_before=NOW,
                limit=10,
            )
        rendered = repr(report)
        assert "deduplication" not in rendered
        assert str(OUTBOX_JOB_B_ID) not in rendered

    asyncio.run(exercise())
