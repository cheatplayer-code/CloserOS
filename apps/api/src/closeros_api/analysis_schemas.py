"""HTTP schemas for tenant analysis query endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AnalysisEvidenceResponse(BaseModel):
    message_id: UUID


class AnalysisCitationResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    retrieval_rank: int
    relevance_basis_points: int


class AnalysisFindingResponse(BaseModel):
    id: UUID
    finding_code: str
    severity: str
    status: str
    confidence_basis_points: int
    created_at: datetime
    evidence: list[AnalysisEvidenceResponse]
    citations: list[AnalysisCitationResponse]


class AnalysisRunResponse(BaseModel):
    id: UUID
    conversation_thread_id: UUID
    status: str
    prompt_version: str
    rubric_version: str
    model_provider: str
    requested_at: datetime
    completed_at: datetime | None
    failure_code: str | None
    findings: list[AnalysisFindingResponse]


class AnalysisRunsResponse(BaseModel):
    runs: list[AnalysisRunResponse]
