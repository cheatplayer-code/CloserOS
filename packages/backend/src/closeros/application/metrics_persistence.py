"""Application persistence ports for metric snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.metrics import MetricScope, MetricSnapshot


class MetricsPersistenceError(PersistenceError):
    """Base class for metrics persistence failures."""


class DuplicateMetricSnapshotError(MetricsPersistenceError):
    """Raised when an identical completed snapshot already exists."""


class MetricSnapshotNotFoundError(MetricsPersistenceError):
    """Raised when a metric snapshot cannot be found."""


class MetricSnapshotRepository(Protocol):
    async def get_completed_snapshot(
        self,
        *,
        tenant_id: UUID,
        scope: MetricScope,
        manager_user_id: UUID | None,
        window_start: datetime,
        window_end: datetime,
        formula_version: str,
    ) -> MetricSnapshot | None: ...

    async def append_completed(
        self,
        *,
        snapshot: MetricSnapshot,
    ) -> None: ...

    async def list_completed(
        self,
        *,
        tenant_id: UUID,
        scope: MetricScope | None = None,
        manager_user_id: UUID | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        formula_version: str | None = None,
        limit: int = 50,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
    ) -> tuple[MetricSnapshot, ...]: ...
