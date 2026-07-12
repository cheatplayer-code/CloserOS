"""HTTP schemas for tenant metrics endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MetricValueResponse(BaseModel):
    key: str
    value: int
    numerator: int | None = None
    denominator: int | None = None


class MetricSnapshotResponse(BaseModel):
    scope: str
    manager_user_id: UUID | None
    window_start: datetime
    window_end: datetime
    window_code: str
    formula_version: str
    computed_at: datetime
    values: list[MetricValueResponse]


class MetricsListResponse(BaseModel):
    snapshots: list[MetricSnapshotResponse]


class MetricsRecalculateAcceptedResponse(BaseModel):
    message: str = Field(default="accepted")
