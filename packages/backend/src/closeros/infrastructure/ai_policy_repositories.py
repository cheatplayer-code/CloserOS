"""PostgreSQL repositories for tenant AI policy and daily usage."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.ai_policy_persistence import (
    AiPolicyPersistenceError,
    AiUsageDailyRecord,
    DuplicateAiPolicyError,
    DuplicateAiUsageDailyError,
    TenantAiPolicyRecord,
)
from closeros.infrastructure import ai_policy_mappers as mappers
from closeros.infrastructure.ai_policy_orm import AiUsageDailyRow, TenantAiPolicyRow
from closeros.infrastructure.persistence_errors import translate_integrity_error

_CONSTRAINT_ERRORS: dict[str, type[AiPolicyPersistenceError]] = {
    "uq_tenant_ai_policies_tenant_id": DuplicateAiPolicyError,
    "uq_ai_usage_daily_tenant_usage_date_dimension_model_provider": DuplicateAiUsageDailyError,
}


def _translate_integrity_error(error: IntegrityError) -> AiPolicyPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=AiPolicyPersistenceError,
        message="ai policy persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyTenantAiPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tenant_id(self, *, tenant_id: UUID) -> TenantAiPolicyRecord | None:
        row = (
            await self._session.execute(
                select(TenantAiPolicyRow).where(TenantAiPolicyRow.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.tenant_ai_policy_to_record(row)

    async def get_by_tenant_id_for_update(
        self,
        *,
        tenant_id: UUID,
    ) -> TenantAiPolicyRecord | None:
        row = (
            await self._session.execute(
                select(TenantAiPolicyRow)
                .where(TenantAiPolicyRow.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.tenant_ai_policy_to_record(row)

    async def upsert(self, *, record: TenantAiPolicyRecord) -> TenantAiPolicyRecord:
        existing = (
            await self._session.execute(
                select(TenantAiPolicyRow)
                .where(TenantAiPolicyRow.tenant_id == record.tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(mappers.tenant_ai_policy_to_row(record))
            await _flush(self._session)
            return record
        existing.mode = record.mode
        existing.prompt_version = record.prompt_version
        existing.rubric_version = record.rubric_version
        existing.minimum_confidence_basis_points = record.minimum_confidence_basis_points
        existing.daily_budget_limit_minor_units = record.daily_budget_limit_minor_units
        existing.monthly_budget_limit_minor_units = record.monthly_budget_limit_minor_units
        existing.updated_at = record.updated_at
        await _flush(self._session)
        return mappers.tenant_ai_policy_to_record(existing)


class SqlAlchemyAiUsageDailyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_usage_key(
        self,
        *,
        tenant_id: UUID,
        usage_date: date,
        dimension: str,
        model_provider: str,
    ) -> AiUsageDailyRecord | None:
        row = (
            await self._session.execute(
                select(AiUsageDailyRow).where(
                    AiUsageDailyRow.tenant_id == tenant_id,
                    AiUsageDailyRow.usage_date == usage_date,
                    AiUsageDailyRow.dimension == dimension,
                    AiUsageDailyRow.model_provider == model_provider,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.ai_usage_daily_to_record(row)

    async def upsert(self, *, record: AiUsageDailyRecord) -> AiUsageDailyRecord:
        existing = (
            await self._session.execute(
                select(AiUsageDailyRow)
                .where(
                    AiUsageDailyRow.tenant_id == record.tenant_id,
                    AiUsageDailyRow.usage_date == record.usage_date,
                    AiUsageDailyRow.dimension == record.dimension,
                    AiUsageDailyRow.model_provider == record.model_provider,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(mappers.ai_usage_daily_to_row(record))
            await _flush(self._session)
            return record
        existing.input_token_count = record.input_token_count
        existing.output_token_count = record.output_token_count
        existing.requests_count = record.requests_count
        existing.cost_minor_units = record.cost_minor_units
        existing.budget_limit_minor_units = record.budget_limit_minor_units
        existing.budget_consumed_basis_points = record.budget_consumed_basis_points
        existing.last_recorded_at = record.last_recorded_at
        await _flush(self._session)
        return mappers.ai_usage_daily_to_record(existing)
