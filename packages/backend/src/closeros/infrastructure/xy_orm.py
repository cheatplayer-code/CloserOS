"""SQLAlchemy ORM models for XY production operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.legal_hold import LegalHoldStatus
from closeros.domain.notification import (
    NotificationAttemptOutcome,
    NotificationDeliveryStatus,
    NotificationKind,
)
from closeros.domain.retention_execution import (
    RetentionPurgeBatchStatus,
    RetentionPurgeRunStatus,
)
from closeros.infrastructure.orm_base import Base

_NOTIFICATION_KIND_VALUES = tuple(kind.value for kind in NotificationKind)
_NOTIFICATION_STATUS_VALUES = tuple(status.value for status in NotificationDeliveryStatus)
_NOTIFICATION_ATTEMPT_OUTCOME_VALUES = tuple(
    outcome.value for outcome in NotificationAttemptOutcome
)
_LEGAL_HOLD_STATUS_VALUES = tuple(status.value for status in LegalHoldStatus)
_RETENTION_RUN_STATUS_VALUES = tuple(status.value for status in RetentionPurgeRunStatus)
_RETENTION_BATCH_STATUS_VALUES = tuple(status.value for status in RetentionPurgeBatchStatus)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class NotificationDeliveryRow(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    payload_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("idempotency_key"),
        ForeignKeyConstraint(
            ["payload_tenant_id", "encrypted_payload_content_id"],
            ["encrypted_contents.tenant_id", "encrypted_contents.id"],
            ondelete="SET NULL",
        ),
        CheckConstraint(f"kind IN ({_quoted(_NOTIFICATION_KIND_VALUES)})", name="kind"),
        CheckConstraint(f"status IN ({_quoted(_NOTIFICATION_STATUS_VALUES)})", name="status"),
        CheckConstraint("template_version >= 1", name="template_version"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        CheckConstraint(
            "("
            "(payload_tenant_id IS NULL AND encrypted_payload_content_id IS NULL) "
            "OR "
            "(payload_tenant_id IS NOT NULL AND encrypted_payload_content_id IS NOT NULL)"
            ")",
            name="payload_reference_pair",
        ),
        Index("ix_notification_deliveries_tenant_status", "tenant_id", "status"),
    )


class NotificationDeliveryAttemptRow(Base):
    __tablename__ = "notification_delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "delivery_id"],
            ["notification_deliveries.tenant_id", "notification_deliveries.id"],
        ),
        CheckConstraint(
            f"outcome IN ({_quoted(_NOTIFICATION_ATTEMPT_OUTCOME_VALUES)})",
            name="outcome",
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number"),
        Index("ix_notification_delivery_attempts_delivery", "tenant_id", "delivery_id"),
    )


class LegalHoldRow(Base):
    __tablename__ = "legal_holds"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint(f"status IN ({_quoted(_LEGAL_HOLD_STATUS_VALUES)})", name="status"),
        Index("ix_legal_holds_tenant_status", "tenant_id", "status"),
    )


class RetentionPurgeRunRow(Base):
    __tablename__ = "retention_purge_runs"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(nullable=False)
    expires_before: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    items_scanned: Mapped[int] = mapped_column(Integer, nullable=False)
    items_deleted: Mapped[int] = mapped_column(Integer, nullable=False)
    items_skipped_legal_hold: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(PostgresUUID(as_uuid=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint(f"status IN ({_quoted(_RETENTION_RUN_STATUS_VALUES)})", name="status"),
        CheckConstraint("items_scanned >= 0", name="items_scanned"),
        CheckConstraint("items_deleted >= 0", name="items_deleted"),
        CheckConstraint("items_skipped_legal_hold >= 0", name="items_skipped_legal_hold"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_retention_purge_runs_tenant_created", "tenant_id", "created_at"),
    )


class RetentionPurgeBatchRow(Base):
    __tablename__ = "retention_purge_batches"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    purge_run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    deleted_content_id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "purge_run_id"],
            ["retention_purge_runs.tenant_id", "retention_purge_runs.id"],
        ),
        CheckConstraint(
            f"status IN ({_quoted(_RETENTION_BATCH_STATUS_VALUES)})",
            name="status",
        ),
        Index("ix_retention_purge_batches_run", "tenant_id", "purge_run_id"),
    )
