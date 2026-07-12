"""Safe tenant API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TenantSummaryResponse(_StrictModel):
    id: UUID
    name: str
    status: Literal["active", "suspended"]
    time_zone: str
    roles: list[str] = Field(min_length=1)


class AuditEventResponse(_StrictModel):
    id: UUID
    scope: Literal["global", "tenant"]
    tenant_id: UUID | None
    actor_type: Literal["anonymous", "user", "system", "service"]
    actor_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    occurred_at: datetime
    correlation_id: UUID


class AuditEventsPageResponse(_StrictModel):
    events: list[AuditEventResponse]
    next_cursor: str | None = None
