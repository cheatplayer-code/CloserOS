"""Domain ↔ ORM mappers for metric snapshot persistence."""

from __future__ import annotations

from uuid import UUID

from closeros.domain.metrics import (
    MetricKey,
    MetricScope,
    MetricSnapshot,
    MetricSnapshotStatus,
    MetricValue,
    MetricWindow,
)
from closeros.infrastructure.metrics_orm import MetricSnapshotRow, MetricValueRow


def to_domain(
    row: MetricSnapshotRow,
    *,
    value_rows: tuple[MetricValueRow, ...],
) -> MetricSnapshot:
    return MetricSnapshot(
        id=row.id,
        tenant_id=row.tenant_id,
        scope=MetricScope(row.scope),
        manager_user_id=row.manager_user_id,
        window=MetricWindow(
            start=row.window_start,
            end=row.window_end,
            window_code=row.window_code,
        ),
        formula_version=row.formula_version,
        source_watermark=row.source_watermark,
        computed_at=row.computed_at,
        status=MetricSnapshotStatus(row.status),
        values=tuple(
            MetricValue(
                key=MetricKey(value_row.metric_key),
                value=value_row.value,
                numerator=value_row.numerator,
                denominator=value_row.denominator,
            )
            for value_row in value_rows
        ),
    )


def to_snapshot_row(snapshot: MetricSnapshot) -> MetricSnapshotRow:
    return MetricSnapshotRow(
        id=snapshot.id,
        tenant_id=snapshot.tenant_id,
        scope=snapshot.scope.value,
        manager_user_id=snapshot.manager_user_id,
        window_start=snapshot.window.start,
        window_end=snapshot.window.end,
        window_code=snapshot.window.window_code,
        formula_version=snapshot.formula_version,
        source_watermark=snapshot.source_watermark,
        computed_at=snapshot.computed_at,
        status=snapshot.status.value,
    )


def to_value_row(*, tenant_id: UUID, snapshot_id: UUID, value: MetricValue) -> MetricValueRow:
    return MetricValueRow(
        snapshot_id=snapshot_id,
        metric_key=value.key.value,
        tenant_id=tenant_id,
        value=value.value,
        numerator=value.numerator,
        denominator=value.denominator,
    )
