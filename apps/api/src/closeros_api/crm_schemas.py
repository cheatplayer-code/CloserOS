"""Pydantic schemas for CRM integration APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CrmConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    provider: str
    portal_domain: str | None
    client_id_ref: str | None
    client_secret_ref: str | None
    access_token_ref: str | None
    refresh_token_ref: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    last_successful_sync_at: datetime | None
    version: int


class CrmConnectionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connections: list[CrmConnectionResponse]


class CreateCrmConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(pattern="^bitrix24$")
    portal_domain: str | None = Field(default=None, max_length=255)
    client_id_ref: str | None = Field(default=None, max_length=64)
    client_secret_ref: str | None = Field(default=None, max_length=64)
    access_token_ref: str | None = Field(default=None, max_length=64)
    refresh_token_ref: str | None = Field(default=None, max_length=64)


class UpdateCrmConnectionRequest(CreateCrmConnectionRequest):
    version: int = Field(ge=1)


class CrmConnectionActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class CrmFieldMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_object_type: str = Field(min_length=1, max_length=64)
    external_field_key: str = Field(min_length=1, max_length=128)
    closeros_field: str = Field(min_length=1, max_length=128)


class CrmFieldMappingResponse(CrmFieldMappingRequest):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    version: int


class CrmFieldMappingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[CrmFieldMappingResponse]


class CrmSyncAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    direction: str
    status: str
    resource_type: str
    started_at: datetime
    finished_at: datetime | None
    records_seen: int
    records_changed: int
    error_code: str | None


class CrmSyncStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[CrmSyncAttemptResponse]


class CrmReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synced_connections: int


class CrmSyncOnceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class CrmConflictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    external_object_type: str
    external_object_id: str
    field_key: str
    crm_value_hash: str
    closeros_value_hash: str
    status: str
    created_at: datetime
    version: int


class CrmConflictListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflicts: list[CrmConflictResponse]


class CrmConflictResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(pattern="^(use_crm|use_closeros|ignore)$")
    version: int = Field(ge=1)
