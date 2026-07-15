"""HTTP schemas for reply suggestions and buyer memory."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReplyCustomerStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    sales_stage: str
    primary_objection: str | None
    urgency: str
    language: str
    missing_information: list[str]


class ReplyNextBestActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: str
    explanation: str


class ReplyProductReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    variant_id: UUID


class ReplySuggestionCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    candidate_key: str
    text: str
    objective: str
    confidence_basis_points: int
    confidence_label: str
    evidence_message_ids: list[UUID]
    product_references: list[ReplyProductReferenceResponse]
    knowledge_citation_ids: list[UUID]
    warnings: list[str]
    is_recommended: bool
    created_at: datetime


class ReplySuggestionRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_thread_id: UUID
    lead_id: UUID | None
    status: str
    prompt_version: str
    rubric_version: str
    provider_code: str | None
    model_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_milliseconds: int | None
    cost_status: str
    estimated_cost_microunits: int | None
    failure_code: str | None
    customer_state: ReplyCustomerStateResponse | None
    next_best_action: ReplyNextBestActionResponse | None
    escalation_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    candidates: list[ReplySuggestionCandidateResponse]


class GenerateReplySuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(default=None, max_length=128)


class SelectReplyCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edited_text: str | None = Field(default=None, max_length=2000)


class ReplySelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    candidate_id: UUID
    outbound_message_id: UUID
    draft_status: str


class BuyerMemoryFactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_thread_id: UUID
    lead_id: UUID | None
    fact_type: str
    normalized_value: str
    display_value: str
    status: str
    confidence_basis_points: int
    confidence_label: str
    source_message_id: UUID | None
    supersedes_fact_id: UUID | None
    observed_at: datetime
    confirmed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class BuyerMemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[BuyerMemoryFactResponse]


class ConfirmBuyerMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_message_id: UUID


class CorrectBuyerMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_value: str = Field(max_length=256)
    display_value: str = Field(max_length=512)
    source_message_id: UUID | None = None
