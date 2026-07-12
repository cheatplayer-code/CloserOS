"""PostgreSQL repository for metric snapshots."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.metrics_persistence import (
    DuplicateMetricSnapshotError,
    MetricsPersistenceError,
)
from closeros.domain.metrics import MetricScope, MetricSnapshot, MetricSnapshotStatus
from closeros.infrastructure import metrics_mappers as mappers
from closeros.infrastructure.metrics_orm import MetricSnapshotRow, MetricValueRow
from closeros.infrastructure.persistence_errors import translate_integrity_error

_CONSTRAINT_ERRORS: dict[str, type[MetricsPersistenceError]] = {
    "uq_metric_snapshots_identity": DuplicateMetricSnapshotError,
}


def _translate_integrity_error(error: IntegrityError) -> MetricsPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=MetricsPersistenceError,
        message="metrics persistence integrity error",
    )


class SqlAlchemyMetricSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_completed_snapshot(
        self,
        *,
        tenant_id: UUID,
        manager_user_id: UUID | None,
        scope: MetricScope,
        window_start: datetime,
        window_end: datetime,
        formula_version: str,
    ) -> MetricSnapshot | None:
        statement = select(MetricSnapshotRow).where(
            MetricSnapshotRow.tenant_id == tenant_id,
            MetricSnapshotRow.scope == scope.value,
            MetricSnapshotRow.manager_user_id == manager_user_id,
            MetricSnapshotRow.window_start == window_start,
            MetricSnapshotRow.window_end == window_end,
            MetricSnapshotRow.formula_version == formula_version,
            MetricSnapshotRow.status == MetricSnapshotStatus.COMPLETED.value,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        value_rows = await self._load_values(tenant_id=tenant_id, snapshot_id=row.id)
        return mappers.to_domain(row, value_rows=value_rows)

    async def append_completed(self, *, snapshot: MetricSnapshot) -> None:
        if snapshot.status is not MetricSnapshotStatus.COMPLETED:
            raise MetricsPersistenceError("only completed snapshots may be appended")
        self._session.add(mappers.to_snapshot_row(snapshot))
        for value in snapshot.values:
            self._session.add(
                mappers.to_value_row(
                    tenant_id=snapshot.tenant_id,
                    snapshot_id=snapshot.id,
                    value=value,
                )
            )
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from error

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
    ) -> tuple[MetricSnapshot, ...]:
        statement = select(MetricSnapshotRow).where(
            MetricSnapshotRow.tenant_id == tenant_id,
            MetricSnapshotRow.status == MetricSnapshotStatus.COMPLETED.value,
        )
        if scope is not None:
            statement = statement.where(MetricSnapshotRow.scope == scope.value)
        if manager_user_id is not None:
            statement = statement.where(MetricSnapshotRow.manager_user_id == manager_user_id)
        if window_start is not None:
            statement = statement.where(MetricSnapshotRow.window_start == window_start)
        if window_end is not None:
            statement = statement.where(MetricSnapshotRow.window_end == window_end)
        if formula_version is not None:
            statement = statement.where(MetricSnapshotRow.formula_version == formula_version)
        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                (MetricSnapshotRow.computed_at < cursor_created_at)
                | (
                    (MetricSnapshotRow.computed_at == cursor_created_at)
                    & (MetricSnapshotRow.id < cursor_id)
                )
            )
        statement = statement.order_by(
            MetricSnapshotRow.computed_at.desc(),
            MetricSnapshotRow.id.desc(),
        ).limit(limit)
        result = await self._session.execute(statement)
        rows = tuple(result.scalars().all())
        snapshots: list[MetricSnapshot] = []
        for row in rows:
            value_rows = await self._load_values(tenant_id=tenant_id, snapshot_id=row.id)
            snapshots.append(mappers.to_domain(row, value_rows=value_rows))
        return tuple(snapshots)

    async def _load_values(
        self,
        *,
        tenant_id: UUID,
        snapshot_id: UUID,
    ) -> tuple[MetricValueRow, ...]:
        statement = (
            select(MetricValueRow)
            .where(
                MetricValueRow.tenant_id == tenant_id,
                MetricValueRow.snapshot_id == snapshot_id,
            )
            .order_by(MetricValueRow.metric_key.asc())
        )
        result = await self._session.execute(statement)
        return tuple(result.scalars().all())
