"""Tests for retention purge and legal hold services."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.retention_purge_service import RetentionPurgeService
from closeros.domain.legal_hold import LegalHoldStatus
from closeros.domain.retention_execution import RetentionPurgeRunStatus

TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")
NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


class _LegalHoldRepo:
    def __init__(self) -> None:
        self.holds = []

    async def get_active_for_tenant(self, *, tenant_id):  # type: ignore[no-untyped-def]
        for hold in self.holds:
            if hold.tenant_id == tenant_id and hold.status is LegalHoldStatus.ACTIVE:
                return hold
        return None

    async def add(self, *, legal_hold) -> None:  # type: ignore[no-untyped-def]
        self.holds.append(legal_hold)

    async def get_by_id(self, *, tenant_id, legal_hold_id):  # type: ignore[no-untyped-def]
        for hold in self.holds:
            if hold.id == legal_hold_id:
                return hold
        return None

    async def update(self, *, legal_hold) -> None:  # type: ignore[no-untyped-def]
        self.holds = [legal_hold if item.id == legal_hold.id else item for item in self.holds]

    async def tenant_has_active_hold(self, *, tenant_id) -> bool:  # type: ignore[no-untyped-def]
        return await self.get_active_for_tenant(tenant_id=tenant_id) is not None


class _EncryptedRepo:
    async def count_due_for_retention(self, *, query_filter):  # type: ignore[no-untyped-def]
        return 2

    async def list_due_for_retention(self, *, query_filter):  # type: ignore[no-untyped-def]
        return (object(), object())


class _PurgeRunRepo:
    def __init__(self) -> None:
        self.runs = []

    async def add(self, *, purge_run) -> None:  # type: ignore[no-untyped-def]
        self.runs.append(purge_run)

    async def get_by_id(self, *, tenant_id, purge_run_id):  # type: ignore[no-untyped-def]
        for run in self.runs:
            if run.id == purge_run_id:
                return run
        return None


class _OutboxRepo:
    async def enqueue(self, job) -> None:  # type: ignore[no-untyped-def]
        return None


class _Uow:
    def __init__(self) -> None:
        self.legal_holds = _LegalHoldRepo()
        self.encrypted_contents = _EncryptedRepo()
        self.retention_purge_runs = _PurgeRunRepo()
        self.outbox_jobs = _OutboxRepo()

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *args) -> None:  # type: ignore[no-untyped-def]
        return None

    async def commit(self) -> None:
        return None


def test_legal_hold_service_creates_active_hold() -> None:
    async def exercise() -> None:
        uow = _Uow()
        service = LegalHoldService(uow_factory=lambda: uow, uuid_factory=uuid4)
        hold = await service.create_hold(
            tenant_id=TENANT_ID,
            reason_code="litigation",
            reason_detail="Case 42",
            created_by_user_id=USER_ID,
            created_at=NOW,
        )
        assert hold.status is LegalHoldStatus.ACTIVE
        assert await service.tenant_has_active_hold(tenant_id=TENANT_ID)

    asyncio.run(exercise())


def test_retention_purge_dry_run_counts_due_items() -> None:
    async def exercise() -> None:
        uow = _Uow()
        legal_hold_service = LegalHoldService(uow_factory=lambda: uow, uuid_factory=uuid4)
        purge_service = RetentionPurgeService(
            uow_factory=lambda: uow,
            uuid_factory=uuid4,
            legal_hold_service=legal_hold_service,
        )
        result = await purge_service.dry_run(
            tenant_id=TENANT_ID,
            expires_before=NOW - timedelta(days=30),
            requested_at=NOW,
        )
        assert result.dry_run is True
        assert result.items_scanned == 2
        assert result.status is RetentionPurgeRunStatus.COMPLETED

    asyncio.run(exercise())
