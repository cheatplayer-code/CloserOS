"""HTTP schemas for tenant knowledge endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeUploadRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=64)
    plaintext_text: str = Field(min_length=1, max_length=5_000_000)


class KnowledgeUploadResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int


class KnowledgeVersionResponse(BaseModel):
    id: UUID
    version_number: int
    status: str
    created_at: datetime
    approved_at: datetime | None
    indexed_at: datetime | None
    revoked_at: datetime | None


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    source_type: str
    source_code: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: KnowledgeVersionResponse | None


class KnowledgeDocumentsResponse(BaseModel):
    documents: list[KnowledgeDocumentResponse]
