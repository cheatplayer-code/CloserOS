"""PostgreSQL claim/lease and legal-hold race tests for retention purge."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from closeros.application.encrypted_content_persistence import EncryptedContentRetentionFilter
from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.retention_purge_handler import (
    RetentionPurgeHandler,
    RetentionPurgeHandlerError,
)
from closeros.domain.encrypted_content import (
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)
from closeros.domain.retention_execution import (
    RetentionPurgeRun,
    RetentionPurgeRunStatus,
)

from tests.auth_persistence_support import USER_ID, synthetic_user
from tests.encryption_support import (
    NOW,
    SYNTHETIC_PLAINTEXT_UTF8,
    build_test_cryptography,
)
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant

pytestmark = pytest.mark.hi_persistence


async def _seed_tenant_and_user(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant(tenant_id=TENANT_A_ID))
        await uow.users.add(synthetic_user(user_id=USER_ID))
        await uow.commit()


async def _seed_due_content(
    integrated_uow_factory: Any,
    *,
    content_id: UUID,
) -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=content_id,
        tenant_id=TENANT_A_ID,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(hours=1),
    )
    uow = integrated_uow_factory()
    async with uow:
        await uow.encrypted_contents.add(encrypted)
        await uow.commit()


async def _create_purge_run(
    integrated_uow_factory: Any,
    *,
    purge_run_id: UUID,
    status: RetentionPurgeRunStatus = RetentionPurgeRunStatus.PENDING,
) -> RetentionPurgeRun:
    run = RetentionPurgeRun(
        id=purge_run_id,
        tenant_id=TENANT_A_ID,
        status=status,
        dry_run=False,
        expires_before=NOW + timedelta(minutes=1),
        items_scanned=0,
        items_deleted=0,
        items_skipped_legal_hold=0,
        started_at=None,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    uow = integrated_uow_factory()
    async with uow:
        await uow.retention_purge_runs.add(purge_run=run)
        await uow.commit()
    return run


def _handler(integrated_uow_factory: Any, *, batch_size: int = 1) -> RetentionPurgeHandler:
    return RetentionPurgeHandler(
        uow_factory=integrated_uow_factory,
        uuid_factory=uuid4,
        legal_hold_service=LegalHoldService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
        ),
        batch_size=batch_size,
    )


def _job(*, purge_run_id: UUID) -> Any:
    return build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_A_ID,
        job_kind=OutboxJobKind.RETENTION_DELETE,
        reference=OutboxJobReference(
            resource_type="retention_purge_run",
            resource_id=purge_run_id,
            schema_version=1,
            tenant_id=TENANT_A_ID,
        ),
        deduplication_key=f"retention-{purge_run_id.hex}-{uuid4().hex[:8]}",
        created_at=NOW,
    )


def test_retention_try_claim_allows_only_one_concurrent_winner(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        token_a = uuid4()
        token_b = uuid4()
        claim_expires = NOW + timedelta(minutes=5)

        async def claim(token: UUID) -> RetentionPurgeRun | None:
            uow = integrated_uow_factory()
            async with uow:
                existing = await uow.retention_purge_runs.get_by_id(
                    tenant_id=TENANT_A_ID,
                    purge_run_id=purge_run_id,
                )
                assert existing is not None
                claimed = await uow.retention_purge_runs.try_claim(
                    tenant_id=TENANT_A_ID,
                    purge_run_id=purge_run_id,
                    claim_token=token,
                    claim_expires_at=claim_expires,
                    now=NOW,
                    expected_version=existing.version,
                )
                await uow.commit()
                return cast(RetentionPurgeRun | None, claimed)

        first, second = await asyncio.gather(claim(token_a), claim(token_b))
        winners = [item for item in (first, second) if item is not None]
        losers = [item for item in (first, second) if item is None]
        assert len(winners) == 1
        assert len(losers) == 1
        assert winners[0].claim_token in {token_a, token_b}
        assert winners[0].status is RetentionPurgeRunStatus.RUNNING

    asyncio.run(exercise())


def test_retention_stale_claim_can_be_recovered(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        purge_run_id = uuid4()
        stale_token = uuid4()
        await _create_purge_run(
            integrated_uow_factory,
            purge_run_id=purge_run_id,
            status=RetentionPurgeRunStatus.RUNNING,
        )
        uow = integrated_uow_factory()
        async with uow:
            existing = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            assert existing is not None
            await uow.retention_purge_runs.update(
                purge_run=replace(
                    existing,
                    claim_token=stale_token,
                    claim_expires_at=NOW - timedelta(minutes=1),
                    updated_at=NOW,
                )
            )
            await uow.commit()

        fresh_token = uuid4()
        uow = integrated_uow_factory()
        async with uow:
            claimed = await uow.retention_purge_runs.try_claim(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
                claim_token=fresh_token,
                claim_expires_at=NOW + timedelta(minutes=5),
                now=NOW,
            )
            await uow.commit()
        assert claimed is not None
        assert claimed.claim_token == fresh_token

    asyncio.run(exercise())


def test_retention_legal_hold_pauses_before_next_deletion(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        await _seed_due_content(integrated_uow_factory, content_id=uuid4())
        await _seed_due_content(integrated_uow_factory, content_id=uuid4())
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)

        legal_holds = LegalHoldService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
        )
        handler = _handler(integrated_uow_factory, batch_size=1)

        await handler.handle(job=_job(purge_run_id=purge_run_id))
        await legal_holds.create_hold(
            tenant_id=TENANT_A_ID,
            reason_code="litigation",
            reason_detail="active matter",
            created_by_user_id=USER_ID,
            created_at=NOW + timedelta(seconds=1),
        )
        await handler.handle(job=_job(purge_run_id=purge_run_id))

        uow = integrated_uow_factory()
        async with uow:
            run = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=10,
                )
            )
        assert run is not None
        assert run.status is RetentionPurgeRunStatus.PAUSED
        assert run.items_deleted == 1
        assert len(remaining) == 1

    asyncio.run(exercise())


def test_retention_cancelled_run_is_not_processed(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        content_id = uuid4()
        await _seed_due_content(integrated_uow_factory, content_id=content_id)
        purge_run_id = uuid4()
        await _create_purge_run(
            integrated_uow_factory,
            purge_run_id=purge_run_id,
            status=RetentionPurgeRunStatus.CANCELLED,
        )
        await _handler(integrated_uow_factory).handle(job=_job(purge_run_id=purge_run_id))
        uow = integrated_uow_factory()
        async with uow:
            run = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            content = await uow.encrypted_contents.get_by_id(
                tenant_id=TENANT_A_ID,
                content_id=content_id,
            )
        assert run is not None
        assert run.status is RetentionPurgeRunStatus.CANCELLED
        assert content is not None

    asyncio.run(exercise())


def test_retention_continuation_is_idempotent_and_completes_when_empty(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        await _seed_due_content(integrated_uow_factory, content_id=uuid4())
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        handler = _handler(integrated_uow_factory, batch_size=10)
        await handler.handle(job=_job(purge_run_id=purge_run_id))
        await handler.handle(job=_job(purge_run_id=purge_run_id))

        uow = integrated_uow_factory()
        async with uow:
            run = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=10,
                )
            )
        assert run is not None
        assert run.status is RetentionPurgeRunStatus.COMPLETED
        assert run.items_deleted == 1
        assert remaining == ()

    asyncio.run(exercise())


def test_duplicate_jobs_cannot_process_same_claim_concurrently(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        content_ids = [uuid4(), uuid4()]
        for content_id in content_ids:
            await _seed_due_content(integrated_uow_factory, content_id=content_id)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        handler = _handler(integrated_uow_factory, batch_size=1)
        job_a = _job(purge_run_id=purge_run_id)
        job_b = _job(purge_run_id=purge_run_id)

        first_result, second_result = await asyncio.gather(
            handler.handle(job=job_a),
            handler.handle(job=job_b),
            return_exceptions=True,
        )
        if isinstance(first_result, RetentionPurgeHandlerError):
            assert first_result.error_code is OutboxErrorCode.STALE_CLAIM
        if isinstance(second_result, RetentionPurgeHandlerError):
            assert second_result.error_code is OutboxErrorCode.STALE_CLAIM

        uow = integrated_uow_factory()
        async with uow:
            run = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=10,
                )
            )
        assert run is not None
        assert run.items_deleted <= len(content_ids)
        assert len(remaining) + run.items_deleted == len(content_ids)

    asyncio.run(exercise())


def test_claim_is_renewed_during_long_batch(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        for _ in range(5):
            await _seed_due_content(integrated_uow_factory, content_id=uuid4())
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)

        handler = _handler(integrated_uow_factory, batch_size=100)
        with (
            patch(
                "closeros.application.retention_purge_handler._RENEW_AFTER_DELETIONS",
                1,
            ),
            patch.object(
                handler,
                "_maybe_renew_claim",
                wraps=handler._maybe_renew_claim,
            ) as renew_spy,
        ):
            await handler.handle(job=_job(purge_run_id=purge_run_id))

        assert renew_spy.await_count >= 1

        uow = integrated_uow_factory()
        async with uow:
            run_after = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
        assert run_after is not None
        assert run_after.items_deleted == 5

    asyncio.run(exercise())


def test_failed_claim_renewal_stops_before_next_delete(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        content_ids = [uuid4() for _ in range(12)]
        for content_id in content_ids:
            await _seed_due_content(integrated_uow_factory, content_id=content_id)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)

        handler = _handler(integrated_uow_factory, batch_size=100)
        claim_token = uuid4()
        claimed = await handler._claim_run(
            tenant_id=TENANT_A_ID,
            purge_run_id=purge_run_id,
            claim_token=claim_token,
            occurred_at=NOW,
        )
        assert claimed is not None

        uow = integrated_uow_factory()
        async with uow:
            due = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=claimed.expires_before,
                    limit=100,
                )
            )
        for index, content in enumerate(due[:10]):
            paused = await handler._delete_content_under_lock(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
                content=content,
                occurred_at=NOW + timedelta(seconds=index),
                items_scanned=index,
                items_deleted=index,
            )
            assert paused is False

        uow = integrated_uow_factory()
        async with uow:
            await uow.retention_purge_runs.update(
                purge_run=replace(
                    claimed,
                    version=claimed.version + 50,
                    updated_at=NOW,
                )
            )
            await uow.commit()

        with pytest.raises(RetentionPurgeHandlerError) as raised:
            await handler._maybe_renew_claim(
                claimed=claimed,
                claim_token=claim_token,
                occurred_at=NOW + timedelta(minutes=4),
                deletions_since_renewal=10,
            )
        assert raised.value.error_code is OutboxErrorCode.STALE_CLAIM

        uow = integrated_uow_factory()
        async with uow:
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=20,
                )
            )
        assert len(remaining) == 2

    asyncio.run(exercise())


def test_legal_hold_creation_serializes_with_retention_delete(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        hold_started = asyncio.Event()
        hold_finished = asyncio.Event()

        async def hold_lock_open() -> None:
            uow = integrated_uow_factory()
            async with uow:
                await uow.retention_purge_runs.acquire_tenant_retention_lock(tenant_id=TENANT_A_ID)
                hold_started.set()
                await asyncio.sleep(1.0)
                await uow.commit()
            hold_finished.set()

        async def create_hold_when_blocked() -> None:
            await hold_started.wait()
            started = time.monotonic()
            legal_holds = LegalHoldService(
                uow_factory=integrated_uow_factory,
                uuid_factory=uuid4,
            )
            await legal_holds.create_hold(
                tenant_id=TENANT_A_ID,
                reason_code="litigation",
                reason_detail="serialize delete",
                created_by_user_id=USER_ID,
                created_at=NOW + timedelta(seconds=1),
            )
            elapsed = time.monotonic() - started
            assert elapsed >= 0.5

        await asyncio.gather(hold_lock_open(), create_hold_when_blocked())
        await hold_finished.wait()

    asyncio.run(exercise())


def test_hold_committed_before_delete_prevents_delete(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        first_id = uuid4()
        second_id = uuid4()
        await _seed_due_content(integrated_uow_factory, content_id=first_id)
        await _seed_due_content(integrated_uow_factory, content_id=second_id)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        handler = _handler(integrated_uow_factory, batch_size=1)
        legal_holds = LegalHoldService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
        )

        await handler.handle(job=_job(purge_run_id=purge_run_id))
        await legal_holds.create_hold(
            tenant_id=TENANT_A_ID,
            reason_code="litigation",
            reason_detail="block second delete",
            created_by_user_id=USER_ID,
            created_at=NOW + timedelta(seconds=1),
        )
        await handler.handle(job=_job(purge_run_id=purge_run_id))

        uow = integrated_uow_factory()
        async with uow:
            run = await uow.retention_purge_runs.get_by_id(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=10,
                )
            )
        assert run is not None
        assert run.status is RetentionPurgeRunStatus.PAUSED
        assert run.items_deleted == 1
        assert len(remaining) == 1

    asyncio.run(exercise())


def test_delete_transaction_committed_before_hold_is_recorded_in_history(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_tenant_and_user(integrated_uow_factory)
        deleted_id = uuid4()
        protected_id = uuid4()
        await _seed_due_content(integrated_uow_factory, content_id=deleted_id)
        await _seed_due_content(integrated_uow_factory, content_id=protected_id)
        purge_run_id = uuid4()
        await _create_purge_run(integrated_uow_factory, purge_run_id=purge_run_id)
        handler = _handler(integrated_uow_factory, batch_size=1)
        legal_holds = LegalHoldService(
            uow_factory=integrated_uow_factory,
            uuid_factory=uuid4,
        )

        await handler.handle(job=_job(purge_run_id=purge_run_id))
        await legal_holds.create_hold(
            tenant_id=TENANT_A_ID,
            reason_code="litigation",
            reason_detail="preserve remaining history",
            created_by_user_id=USER_ID,
            created_at=NOW + timedelta(seconds=1),
        )

        uow = integrated_uow_factory()
        async with uow:
            batches = await uow.retention_purge_batches.list_for_run(
                tenant_id=TENANT_A_ID,
                purge_run_id=purge_run_id,
            )
            remaining = await uow.encrypted_contents.list_due_for_retention(
                query_filter=EncryptedContentRetentionFilter(
                    tenant_id=TENANT_A_ID,
                    expires_before=NOW + timedelta(minutes=1),
                    limit=10,
                )
            )
        assert len(batches) == 1
        assert len(remaining) == 1
        assert batches[0].deleted_content_id != remaining[0].id

    asyncio.run(exercise())
