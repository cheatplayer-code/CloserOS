"""SQLAlchemy ORM models for WhatsApp Cloud connections and templates."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.provider_template import ProviderTemplateApprovalStatus
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnectionStatus,
)
from closeros.infrastructure.orm_base import Base

_CONNECTION_STATUS_VALUES = tuple(status.value for status in WhatsAppCloudConnectionStatus)
_WEBHOOK_SUBSCRIPTION_STATUS_VALUES = tuple(status.value for status in WebhookSubscriptionStatus)
_TEMPLATE_APPROVAL_STATUS_VALUES = tuple(status.value for status in ProviderTemplateApprovalStatus)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class WhatsAppCloudConnectionRow(Base):
    __tablename__ = "whatsapp_cloud_connections"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    graph_api_version: Mapped[str] = mapped_column(String(16), nullable=False)
    access_token_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_secret_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verify_token_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    webhook_subscription_status: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    webhook_public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "phone_number_id"),
        UniqueConstraint("webhook_public_key"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        CheckConstraint(
            f"provider = '{ProviderKind.WHATSAPP_CLOUD.value}'",
            name="provider",
        ),
        CheckConstraint(f"status IN ({_quoted(_CONNECTION_STATUS_VALUES)})", name="status"),
        CheckConstraint(
            f"webhook_subscription_status IN ({_quoted(_WEBHOOK_SUBSCRIPTION_STATUS_VALUES)})",
            name="webhook_subscription_status",
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("jsonb_typeof(capabilities) = 'array'", name="capabilities_array"),
        Index("ix_whatsapp_cloud_connections_tenant_id_status", "tenant_id", "status"),
    )


class ProviderMessageTemplateRow(Base):
    __tablename__ = "provider_message_templates"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    whatsapp_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    provider_template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False)
    component_shape: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    parameter_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "whatsapp_connection_id", "provider_template_id"),
        ForeignKeyConstraint(
            ["tenant_id", "whatsapp_connection_id"],
            ["whatsapp_cloud_connections.tenant_id", "whatsapp_cloud_connections.id"],
        ),
        CheckConstraint(
            f"approval_status IN ({_quoted(_TEMPLATE_APPROVAL_STATUS_VALUES)})",
            name="approval_status",
        ),
        CheckConstraint("parameter_count >= 0", name="parameter_count"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("jsonb_typeof(component_shape) = 'array'", name="component_shape_array"),
        Index(
            "ix_provider_message_templates_tenant_connection_name",
            "tenant_id",
            "whatsapp_connection_id",
            "name",
        ),
    )
