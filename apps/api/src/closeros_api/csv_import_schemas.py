"""Pydantic schemas for CSV import HTTP routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CsvImportPreviewColumnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    label: str


class CsvImportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: UUID
    columns: list[CsvImportPreviewColumnResponse]
    total_rows: int


class CsvImportStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping: dict[str, int] = Field(min_length=1)


class CsvImportStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: UUID
    outbox_job_id: UUID


class CsvImportRowErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int
    error_code: str
    field_name: str | None = None


class CsvImportStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: UUID
    status: str
    total_rows: int
    succeeded_count: int
    failed_count: int
    next_row_number: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    row_errors: list[CsvImportRowErrorResponse]


class CsvImportAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "accepted"
