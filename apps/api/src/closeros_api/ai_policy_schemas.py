"""HTTP schemas for tenant AI policy endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AiPolicyResponse(BaseModel):
    mode: str
    prompt_version: str
    rubric_version: str
    minimum_confidence_basis_points: int
    daily_budget_limit_minor_units: int
    monthly_budget_limit_minor_units: int
    updated_at: datetime


class AiPolicyUpdateRequest(BaseModel):
    mode: str = Field(pattern="^(off|observe|enforce)$")
    prompt_version: str = Field(min_length=1, max_length=64)
    rubric_version: str = Field(min_length=1, max_length=64)
    minimum_confidence_basis_points: int = Field(ge=0, le=10_000)
    daily_budget_limit_minor_units: int = Field(ge=0)
    monthly_budget_limit_minor_units: int = Field(ge=0)
