"""SQLAlchemy ORM models for tenant AI policy and daily usage."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_POLICY_MODE_VALUES = ("off", "observe", "enforce")
_USAGE_DIMENSION_VALUES = ("analysis", "retrieval")
_MODEL_PROVIDER_VALUES = ("deepseek", "openai", "anthropic", "local")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class TenantAiPolicyRow(Base):
    __tablename__ = "tenant_ai_policies"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    minimum_confidence_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_budget_limit_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_budget_limit_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        ForeignKeyConstraint(("tenant_id",), ("tenants.id",)),
        CheckConstraint(f"mode IN ({_quoted(_POLICY_MODE_VALUES)})", name="mode"),
        CheckConstraint(
            "minimum_confidence_basis_points >= 0 AND minimum_confidence_basis_points <= 10000",
            name="minimum_confidence_basis_points",
        ),
        CheckConstraint(
            "daily_budget_limit_minor_units >= 0", name="daily_budget_limit_non_negative"
        ),
        CheckConstraint(
            "monthly_budget_limit_minor_units >= 0",
            name="monthly_budget_limit_non_negative",
        ),
        Index("ix_tenant_ai_policies_tenant_id_updated_at", "tenant_id", "updated_at"),
    )


class AiUsageDailyRow(Base):
    __tablename__ = "ai_usage_daily"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    input_token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    output_token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_limit_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_consumed_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    last_recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "usage_date", "dimension", "model_provider"),
        ForeignKeyConstraint(("tenant_id",), ("tenants.id",)),
        CheckConstraint(f"dimension IN ({_quoted(_USAGE_DIMENSION_VALUES)})", name="dimension"),
        CheckConstraint(
            f"model_provider IN ({_quoted(_MODEL_PROVIDER_VALUES)})", name="model_provider"
        ),
        CheckConstraint("input_token_count >= 0", name="input_token_count_non_negative"),
        CheckConstraint("output_token_count >= 0", name="output_token_count_non_negative"),
        CheckConstraint("requests_count >= 0", name="requests_count_non_negative"),
        CheckConstraint("cost_minor_units >= 0", name="cost_minor_units_non_negative"),
        CheckConstraint(
            "budget_limit_minor_units >= 0",
            name="budget_limit_minor_units_non_negative",
        ),
        CheckConstraint(
            "budget_consumed_basis_points >= 0 AND budget_consumed_basis_points <= 10000",
            name="budget_consumed_basis_points",
        ),
        Index("ix_ai_usage_daily_tenant_usage_date", "tenant_id", "usage_date"),
        Index(
            "ix_ai_usage_daily_tenant_budget_bps",
            "tenant_id",
            "budget_consumed_basis_points",
            "usage_date",
        ),
    )
