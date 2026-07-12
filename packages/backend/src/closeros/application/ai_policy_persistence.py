"""Application persistence ports for tenant AI policy and daily AI usage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError


class AiPolicyPersistenceError(PersistenceError):
    """Base class for safe AI policy persistence failures."""


class AiPolicyNotFoundError(AiPolicyPersistenceError):
    """Raised when a tenant AI policy does not exist."""


class DuplicateAiPolicyError(AiPolicyPersistenceError):
    """Raised when tenant AI policy uniqueness is violated."""


class DuplicateAiUsageDailyError(AiPolicyPersistenceError):
    """Raised when daily AI usage uniqueness is violated."""


@dataclass(frozen=True, slots=True)
class TenantAiPolicyRecord:
    id: UUID
    tenant_id: UUID
    mode: str
    prompt_version: str
    rubric_version: str
    minimum_confidence_basis_points: int
    daily_budget_limit_minor_units: int
    monthly_budget_limit_minor_units: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AiUsageDailyRecord:
    id: UUID
    tenant_id: UUID
    usage_date: date
    dimension: str
    model_provider: str
    input_token_count: int
    output_token_count: int
    requests_count: int
    cost_minor_units: int
    budget_limit_minor_units: int
    budget_consumed_basis_points: int
    last_recorded_at: datetime


class TenantAiPolicyRepository(Protocol):
    async def get_by_tenant_id(self, *, tenant_id: UUID) -> TenantAiPolicyRecord | None: ...

    async def get_by_tenant_id_for_update(
        self,
        *,
        tenant_id: UUID,
    ) -> TenantAiPolicyRecord | None: ...

    async def upsert(self, *, record: TenantAiPolicyRecord) -> TenantAiPolicyRecord: ...


class AiUsageDailyRepository(Protocol):
    async def get_by_usage_key(
        self,
        *,
        tenant_id: UUID,
        usage_date: date,
        dimension: str,
        model_provider: str,
    ) -> AiUsageDailyRecord | None: ...

    async def upsert(self, *, record: AiUsageDailyRecord) -> AiUsageDailyRecord: ...
