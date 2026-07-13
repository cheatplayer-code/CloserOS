"""SQLAlchemy ORM models for outbound messages and media references."""

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
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.outbound_message import OutboundMessageKind, OutboundMessageStatus
from closeros.domain.provider_media_reference import MediaQuarantineStatus
from closeros.infrastructure.orm_base import Base

_OUTBOUND_KIND_VALUES = tuple(kind.value for kind in OutboundMessageKind)
_OUTBOUND_STATUS_VALUES = tuple(status.value for status in OutboundMessageStatus)
_MEDIA_QUARANTINE_STATUS_VALUES = tuple(status.value for status in MediaQuarantineStatus)
_DELIVERY_ATTEMPT_OUTCOME_VALUES = ("succeeded", "failed", "delivery_unknown")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ProviderMediaReferenceRow(Base):
    __tablename__ = "provider_media_references"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    inbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    provider_media_id: Mapped[str] = mapped_column(String(128), nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encrypted_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    quarantine_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "channel_connection_id", "provider_media_id"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inbound_message_id"],
            ["messages.tenant_id", "messages.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "encrypted_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        CheckConstraint(
            f"quarantine_status IN ({_quoted(_MEDIA_QUARANTINE_STATUS_VALUES)})",
            name="quarantine_status",
        ),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes"),
        Index(
            "ix_provider_media_references_tenant_thread_id", "tenant_id", "conversation_thread_id"
        ),
    )


class OutboundMessageRow(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    conversation_thread_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_content_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    provider_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_thread_id"],
            ["conversation_threads.tenant_id", "conversation_threads.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "encrypted_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "provider_template_id"],
            ["provider_message_templates.tenant_id", "provider_message_templates.id"],
        ),
        CheckConstraint(f"kind IN ({_quoted(_OUTBOUND_KIND_VALUES)})", name="kind"),
        CheckConstraint(f"status IN ({_quoted(_OUTBOUND_STATUS_VALUES)})", name="status"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_outbound_messages_tenant_status_updated_at", "tenant_id", "status", "updated_at"),
        Index("ix_outbound_messages_tenant_thread_id", "tenant_id", "conversation_thread_id"),
    )


class OutboundDeliveryAttemptRow(Base):
    __tablename__ = "outbound_delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    outbound_message_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "outbound_message_id", "attempt_number"),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_message_id"],
            ["outbound_messages.tenant_id", "outbound_messages.id"],
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number"),
        CheckConstraint(
            f"outcome IN ({_quoted(_DELIVERY_ATTEMPT_OUTCOME_VALUES)})",
            name="outcome",
        ),
        CheckConstraint("finished_at >= started_at", name="finished_at"),
    )
