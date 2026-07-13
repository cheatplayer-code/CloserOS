"""Application ports for legal hold and retention purge persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.legal_hold import LegalHold, LegalHoldStatus
from closeros.domain.retention_execution import (
    RetentionPurgeBatch,
    RetentionPurgeBatchStatus,
    RetentionPurgeRun,
)


class RetentionPersistenceError(PersistenceError):
    """Base class for retention persistence failures."""


class LegalHoldNotFoundError(RetentionPersistenceError):
    """Raised when a legal hold does not exist."""


class RetentionPurgeRunNotFoundError(RetentionPersistenceError):
    """Raised when a retention purge run does not exist."""


@dataclass(frozen=True, slots=True)
class LegalHoldFilter:
    tenant_id: UUID
    status: LegalHoldStatus | None = None


class LegalHoldRepository(Protocol):
    async def add(self, *, legal_hold: LegalHold) -> None: ...

    async def get_active_for_tenant(
        self,
        *,
        tenant_id: UUID,
    ) -> LegalHold | None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        legal_hold_id: UUID,
    ) -> LegalHold | None: ...

    async def update(self, *, legal_hold: LegalHold) -> None: ...

    async def tenant_has_active_hold(self, *, tenant_id: UUID) -> bool: ...


class RetentionPurgeRunRepository(Protocol):
    async def add(self, *, purge_run: RetentionPurgeRun) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
    ) -> RetentionPurgeRun | None: ...

    async def update(self, *, purge_run: RetentionPurgeRun) -> None: ...

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
    ) -> tuple[RetentionPurgeRun, ...]: ...

    async def try_claim(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        claim_token: UUID,
        claim_expires_at: datetime,
        now: datetime,
        expected_version: int | None = None,
    ) -> RetentionPurgeRun | None: ...

    async def renew_claim(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
        claim_token: UUID,
        claim_expires_at: datetime,
        now: datetime,
        expected_version: int,
    ) -> RetentionPurgeRun | None: ...

    async def acquire_tenant_retention_lock(self, *, tenant_id: UUID) -> None: ...


class RetentionPurgeBatchRepository(Protocol):
    async def add(self, *, batch: RetentionPurgeBatch) -> None: ...

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        purge_run_id: UUID,
    ) -> tuple[RetentionPurgeBatch, ...]: ...

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        batch_id: UUID,
        status: RetentionPurgeBatchStatus,
        completed_at: datetime | None,
    ) -> None: ...


__all__ = [
    "LegalHoldFilter",
    "LegalHoldNotFoundError",
    "LegalHoldRepository",
    "RetentionPersistenceError",
    "RetentionPurgeBatchRepository",
    "RetentionPurgeRunNotFoundError",
    "RetentionPurgeRunRepository",
]
