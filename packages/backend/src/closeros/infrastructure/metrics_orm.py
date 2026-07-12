"""SQLAlchemy ORM models for metric snapshot persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.metrics import MetricKey, MetricScope, MetricSnapshotStatus
from closeros.infrastructure.orm_base import Base

_SCOPE_VALUES = tuple(scope.value for scope in MetricScope)
_STATUS_VALUES = tuple(status.value for status in MetricSnapshotStatus)
_METRIC_KEY_VALUES = tuple(key.value for key in MetricKey)


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class MetricSnapshotRow(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    window_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    window_code: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_watermark: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "scope",
            "manager_user_id",
            "window_start",
            "window_end",
            "formula_version",
            name="uq_metric_snapshots_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_metric_snapshots_tenant",
        ),
        CheckConstraint(
            f"scope IN ({_quoted_values(_SCOPE_VALUES)})",
            name="scope",
        ),
        CheckConstraint(
            f"status IN ({_quoted_values(_STATUS_VALUES)})",
            name="status",
        ),
        CheckConstraint("window_end > window_start", name="window_range_valid"),
        CheckConstraint(
            "(scope = 'tenant' AND manager_user_id IS NULL) OR "
            "(scope = 'manager' AND manager_user_id IS NOT NULL)",
            name="scope_manager_consistency",
        ),
        Index("ix_metric_snapshots_tenant_computed_at", "tenant_id", "computed_at"),
        Index(
            "ix_metric_snapshots_tenant_window",
            "tenant_id",
            "window_start",
            "window_end",
        ),
    )


class MetricValueRow(Base):
    __tablename__ = "metric_values"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    numerator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denominator: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["metric_snapshots.tenant_id", "metric_snapshots.id"],
            name="fk_metric_values_snapshot",
        ),
        CheckConstraint(
            f"metric_key IN ({_quoted_values(_METRIC_KEY_VALUES)})",
            name="metric_key",
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint(
            "numerator IS NULL OR numerator >= 0",
            name="numerator_non_negative",
        ),
        CheckConstraint(
            "denominator IS NULL OR denominator >= 0",
            name="denominator_non_negative",
        ),
        CheckConstraint(
            "(metric_key LIKE '%basis_points' AND value <= 10000) OR "
            "metric_key NOT LIKE '%basis_points'",
            name="basis_points_bounds",
        ),
        Index("ix_metric_values_tenant_snapshot", "tenant_id", "snapshot_id"),
    )
