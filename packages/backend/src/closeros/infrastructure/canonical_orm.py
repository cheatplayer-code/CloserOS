"""SQLAlchemy ORM models for canonical conversation entities.

These models are the only representation that touches the database. They store
metadata and references only: no message bodies, text, or raw provider payloads.
Adapter metadata is stored as JSONB. Parent tables expose composite uniqueness on
``(tenant_id, id)`` so child foreign keys can enforce tenant-safe references.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    CrmOutcomeType,
    DeliveryStatus,
    LeadStatus,
    MessageDirection,
    ParticipantSenderType,
    ProviderKind,
    SalesCaseStatus,
    WebhookProcessingStatus,
)
from closeros.infrastructure.orm_base import Base

_PROVIDER_VALUES = tuple(provider.value for provider in ProviderKind)
_CHANNEL_CONNECTION_STATUS_VALUES = tuple(status.value for status in ChannelConnectionStatus)
_LEAD_STATUS_VALUES = tuple(status.value for status in LeadStatus)
_SALES_CASE_STATUS_VALUES = tuple(status.value for status in SalesCaseStatus)
_SENDER_TYPE_VALUES = tuple(sender_type.value for sender_type in ParticipantSenderType)
_MESSAGE_DIRECTION_VALUES = tuple(direction.value for direction in MessageDirection)
_DELIVERY_STATUS_VALUES = tuple(status.value for status in DeliveryStatus)
_CRM_OUTCOME_TYPE_VALUES = tuple(outcome_type.value for outcome_type in CrmOutcomeType)
_WEBHOOK_PROCESSING_STATUS_VALUES = tuple(status.value for status in WebhookProcessingStatus)

_EXTERNAL_ID_LENGTH = 256


def _adapter_metadata_object_check() -> CheckConstraint:
    return CheckConstraint(
        "jsonb_typeof(adapter_metadata) = 'object'",
        name="adapter_metadata_object",
    )


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ChannelConnectionRow(Base):
    __tablename__ = "channel_connections"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_connection_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_connection_id",
        ),
        CheckConstraint(
            f"provider IN ({_quoted_values(_PROVIDER_VALUES)})",
            name="provider",
        ),
        CheckConstraint(
            f"status IN ({_quoted_values(_CHANNEL_CONNECTION_STATUS_VALUES)})",
            name="status",
        ),
        _adapter_metadata_object_check(),
        Index("ix_channel_connections_tenant_id", "tenant_id"),
    )


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_identity_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "external_identity_id"),
        CheckConstraint(
            f"status IN ({_quoted_values(_LEAD_STATUS_VALUES)})",
            name="status",
        ),
        _adapter_metadata_object_check(),
        Index("ix_leads_tenant_id", "tenant_id"),
    )


class SalesCaseRow(Base):
    __tablename__ = "sales_cases"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            f"status IN ({_quoted_values(_SALES_CASE_STATUS_VALUES)})",
            name="status",
        ),
        Index("ix_sales_cases_tenant_id", "tenant_id"),
    )


class ConversationThreadRow(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    external_conversation_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    sales_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    lifecycle_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
        ),
        UniqueConstraint(
            "tenant_id",
            "channel_connection_id",
            "external_conversation_id",
        ),
        CheckConstraint(
            f"lifecycle_status IS NULL OR lifecycle_status IN "
            f"({_quoted_values(_SALES_CASE_STATUS_VALUES)})",
            name="lifecycle_status",
        ),
        CheckConstraint(
            "sales_case_id IS NULL OR lifecycle_status IS NULL",
            name="sales_case_lifecycle",
        ),
        _adapter_metadata_object_check(),
        Index("ix_conversation_threads_tenant_id", "tenant_id"),
        Index(
            "ix_conversation_threads_tenant_id_channel_connection_id",
            "tenant_id",
            "channel_connection_id",
        ),
    )


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    external_message_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reply_to_message_id"],
            ["messages.tenant_id", "messages.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        UniqueConstraint(
            "tenant_id",
            "conversation_thread_id",
            "external_message_id",
        ),
        CheckConstraint(
            f"sender_type IN ({_quoted_values(_SENDER_TYPE_VALUES)})",
            name="sender_type",
        ),
        CheckConstraint(
            f"direction IN ({_quoted_values(_MESSAGE_DIRECTION_VALUES)})",
            name="direction",
        ),
        CheckConstraint("received_at >= sent_at", name="received_at_not_before_sent_at"),
        _adapter_metadata_object_check(),
        Index(
            "ix_messages_tenant_id_conversation_thread_id", "tenant_id", "conversation_thread_id"
        ),
    )


class MessageEditEventRow(Base):
    __tablename__ = "message_edit_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_event_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        UniqueConstraint("tenant_id", "external_event_id"),
        _adapter_metadata_object_check(),
        Index("ix_message_edit_events_tenant_id_message_id", "tenant_id", "message_id"),
    )


class MessageDeletionEventRow(Base):
    __tablename__ = "message_deletion_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_event_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
        ),
        UniqueConstraint("tenant_id", "external_event_id"),
        _adapter_metadata_object_check(),
        Index(
            "ix_message_deletion_events_tenant_id_message_id",
            "tenant_id",
            "message_id",
        ),
    )


class MessageDeliveryStatusEventRow(Base):
    __tablename__ = "message_delivery_status_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_event_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
        ),
        UniqueConstraint("tenant_id", "external_event_id"),
        CheckConstraint(
            f"delivery_status IN ({_quoted_values(_DELIVERY_STATUS_VALUES)})",
            name="delivery_status",
        ),
        _adapter_metadata_object_check(),
        Index(
            "ix_message_delivery_status_events_tenant_id_message_id",
            "tenant_id",
            "message_id",
        ),
    )


class ManagerAssignmentRow(Base):
    __tablename__ = "manager_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    manager_user_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    sales_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "manager_user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_manager_assignments_tenant_manager_user_memberships",
        ),
        CheckConstraint(
            "(conversation_thread_id IS NOT NULL AND sales_case_id IS NULL) OR "
            "(conversation_thread_id IS NULL AND sales_case_id IS NOT NULL)",
            name="assignment_target",
        ),
        Index("ix_manager_assignments_tenant_id", "tenant_id"),
        Index(
            "ix_manager_assignments_tenant_id_conversation_thread_id",
            "tenant_id",
            "conversation_thread_id",
        ),
        Index(
            "ix_manager_assignments_tenant_id_sales_case_id",
            "tenant_id",
            "sales_case_id",
        ),
    )


class CRMOutcomeRow(Base):
    __tablename__ = "crm_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    sales_case_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_deal_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    outcome_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "sales_case_id"],
            ["sales_cases.tenant_id", "sales_cases.id"],
        ),
        UniqueConstraint("tenant_id", "external_deal_id"),
        CheckConstraint(
            f"outcome_type IN ({_quoted_values(_CRM_OUTCOME_TYPE_VALUES)})",
            name="outcome_type",
        ),
        _adapter_metadata_object_check(),
        Index("ix_crm_outcomes_tenant_id_sales_case_id", "tenant_id", "sales_case_id"),
    )


class WebhookEventRow(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    external_event_id: Mapped[str] = mapped_column(
        String(_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    encrypted_payload_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )
    adapter_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "encrypted_payload_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        UniqueConstraint(
            "tenant_id",
            "channel_connection_id",
            "external_event_id",
        ),
        CheckConstraint(
            f"processing_status IN ({_quoted_values(_WEBHOOK_PROCESSING_STATUS_VALUES)})",
            name="processing_status",
        ),
        CheckConstraint(
            "processed_at IS NULL OR processed_at >= received_at",
            name="processed_at_not_before_received_at",
        ),
        _adapter_metadata_object_check(),
        Index(
            "ix_webhook_events_tenant_id_channel_connection_id",
            "tenant_id",
            "channel_connection_id",
        ),
    )
