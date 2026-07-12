"""Pydantic schemas for WhatsApp integration and outbound messaging APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    channel_connection_id: UUID
    provider: str
    app_id: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str | None
    graph_api_version: str
    access_token_ref: str | None
    app_secret_ref: str | None
    verify_token_ref: str | None
    status: str
    webhook_subscription_status: str
    capabilities: list[str]
    webhook_public_key: str
    webhook_callback_path: str
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    version: int


class WhatsAppConnectionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connections: list[WhatsAppConnectionResponse]


class CreateWhatsAppConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=1, max_length=64)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    display_phone_number: str | None = Field(default=None, max_length=32)
    graph_api_version: str = Field(default="v21.0", max_length=16)
    access_token_ref: str | None = Field(default=None, max_length=64)
    app_secret_ref: str | None = Field(default=None, max_length=64)
    verify_token_ref: str | None = Field(default=None, max_length=64)


class UpdateWhatsAppConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    app_id: str = Field(min_length=1, max_length=64)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    display_phone_number: str | None = Field(default=None, max_length=32)
    graph_api_version: str = Field(min_length=1, max_length=16)
    access_token_ref: str | None = Field(default=None, max_length=64)
    app_secret_ref: str | None = Field(default=None, max_length=64)
    verify_token_ref: str | None = Field(default=None, max_length=64)


class WhatsAppConnectionActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class ProviderTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    whatsapp_connection_id: UUID
    provider_template_id: str
    name: str
    language_code: str
    category: str
    approval_status: str
    component_shape: list[str]
    parameter_count: int
    last_synced_at: datetime
    version: int


class ProviderTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    templates: list[ProviderTemplateResponse]


class OutboundMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_thread_id: UUID
    channel_connection_id: UUID
    kind: str
    status: str
    provider_template_id: UUID | None
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    failure_code: str | None
    created_at: datetime
    approved_at: datetime | None
    queued_at: datetime | None
    sent_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    version: int


class CreateOutboundDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    body_text: str | None = Field(default=None, max_length=4096)
    provider_template_id: UUID | None = None
    template_parameters: list[str] | None = Field(default=None, max_length=10)


class OutboundMessageActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
