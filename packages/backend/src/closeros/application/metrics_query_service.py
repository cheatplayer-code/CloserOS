"""Tenant-scoped metrics query service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.metrics import METRIC_FORMULA_VERSION, MetricScope, MetricSnapshot

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


class MetricsQueryUnavailableError(Exception):
    """Raised when metrics query cannot be completed."""


class MetricsQueryService:
    def __init__(self, *, uow_factory: _UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list_snapshots(
        self,
        *,
        tenant_id: UUID,
        scope: MetricScope,
        manager_user_id: UUID | None,
        window_start: datetime | None,
        window_end: datetime | None,
        formula_version: str | None,
        limit: int = 50,
    ) -> tuple[MetricSnapshot, ...]:
        uow = self._uow_factory()
        async with uow:
            return await uow.metric_snapshots.list_completed(
                tenant_id=tenant_id,
                scope=scope,
                manager_user_id=manager_user_id,
                window_start=window_start,
                window_end=window_end,
                formula_version=formula_version or METRIC_FORMULA_VERSION,
                limit=limit,
            )
