"""Mappers between AI policy persistence records and ORM rows."""

from __future__ import annotations

from closeros.application.ai_policy_persistence import (
    AiUsageDailyRecord,
    TenantAiPolicyRecord,
)
from closeros.infrastructure.ai_policy_orm import AiUsageDailyRow, TenantAiPolicyRow


def tenant_ai_policy_to_row(record: TenantAiPolicyRecord) -> TenantAiPolicyRow:
    return TenantAiPolicyRow(
        id=record.id,
        tenant_id=record.tenant_id,
        mode=record.mode,
        prompt_version=record.prompt_version,
        rubric_version=record.rubric_version,
        minimum_confidence_basis_points=record.minimum_confidence_basis_points,
        daily_budget_limit_minor_units=record.daily_budget_limit_minor_units,
        monthly_budget_limit_minor_units=record.monthly_budget_limit_minor_units,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def tenant_ai_policy_to_record(row: TenantAiPolicyRow) -> TenantAiPolicyRecord:
    return TenantAiPolicyRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        mode=row.mode,
        prompt_version=row.prompt_version,
        rubric_version=row.rubric_version,
        minimum_confidence_basis_points=row.minimum_confidence_basis_points,
        daily_budget_limit_minor_units=row.daily_budget_limit_minor_units,
        monthly_budget_limit_minor_units=row.monthly_budget_limit_minor_units,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def ai_usage_daily_to_row(record: AiUsageDailyRecord) -> AiUsageDailyRow:
    return AiUsageDailyRow(
        id=record.id,
        tenant_id=record.tenant_id,
        usage_date=record.usage_date,
        dimension=record.dimension,
        model_provider=record.model_provider,
        input_token_count=record.input_token_count,
        output_token_count=record.output_token_count,
        requests_count=record.requests_count,
        cost_minor_units=record.cost_minor_units,
        budget_limit_minor_units=record.budget_limit_minor_units,
        budget_consumed_basis_points=record.budget_consumed_basis_points,
        last_recorded_at=record.last_recorded_at,
    )


def ai_usage_daily_to_record(row: AiUsageDailyRow) -> AiUsageDailyRecord:
    return AiUsageDailyRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        usage_date=row.usage_date,
        dimension=row.dimension,
        model_provider=row.model_provider,
        input_token_count=row.input_token_count,
        output_token_count=row.output_token_count,
        requests_count=row.requests_count,
        cost_minor_units=row.cost_minor_units,
        budget_limit_minor_units=row.budget_limit_minor_units,
        budget_consumed_basis_points=row.budget_consumed_basis_points,
        last_recorded_at=row.last_recorded_at,
    )
