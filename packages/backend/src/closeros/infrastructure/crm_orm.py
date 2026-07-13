"""SQLAlchemy ORM models for CRM integrations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.domain.crm_conflict import CrmConflictResolution, CrmConflictStatus
from closeros.domain.crm_connection import CrmConnectionStatus
from closeros.domain.crm_field_mapping import CrmFieldMappingStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.crm_sync import CrmSyncAttemptStatus, CrmSyncDirection
from closeros.infrastructure.orm_base import Base


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_PROVIDER_VALUES = tuple(item.value for item in CrmProviderCode)
_CONNECTION_STATUS_VALUES = tuple(item.value for item in CrmConnectionStatus)
_MAPPING_STATUS_VALUES = tuple(item.value for item in CrmFieldMappingStatus)
_SYNC_DIRECTION_VALUES = tuple(item.value for item in CrmSyncDirection)
_ATTEMPT_STATUS_VALUES = tuple(item.value for item in CrmSyncAttemptStatus)
_CONFLICT_STATUS_VALUES = tuple(item.value for item in CrmConflictStatus)
_CONFLICT_RESOLUTION_VALUES = tuple(item.value for item in CrmConflictResolution)


class CrmConnectionRow(Base):
    __tablename__ = "crm_connections"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    portal_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_id_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_secret_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_token_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refresh_token_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "provider", "portal_domain"),
        CheckConstraint(f"provider IN ({_quoted(_PROVIDER_VALUES)})", name="provider"),
        CheckConstraint(f"status IN ({_quoted(_CONNECTION_STATUS_VALUES)})", name="status"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_crm_connections_tenant_status", "tenant_id", "status"),
    )


class CrmFieldMappingRow(Base):
    __tablename__ = "crm_field_mappings"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    crm_connection_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    closeros_field: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "crm_connection_id",
            "external_object_type",
            "external_field_key",
        ),
        CheckConstraint(f"status IN ({_quoted(_MAPPING_STATUS_VALUES)})", name="status"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_crm_field_mappings_tenant_connection", "tenant_id", "crm_connection_id"),
    )


class CrmSyncCheckpointRow(Base):
    __tablename__ = "crm_sync_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    crm_connection_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "crm_connection_id", "direction", "resource_type"),
        CheckConstraint(
            f"direction IN ({_quoted(_SYNC_DIRECTION_VALUES)})",
            name="direction",
        ),
        CheckConstraint("version >= 1", name="version"),
    )


class CrmSyncAttemptRow(Base):
    __tablename__ = "crm_sync_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    crm_connection_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False)
    records_changed: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(f"direction IN ({_quoted(_SYNC_DIRECTION_VALUES)})", name="direction"),
        CheckConstraint(f"status IN ({_quoted(_ATTEMPT_STATUS_VALUES)})", name="status"),
        CheckConstraint("records_seen >= 0", name="records_seen"),
        CheckConstraint("records_changed >= 0", name="records_changed"),
        Index(
            "ix_crm_sync_attempts_tenant_connection_started",
            "tenant_id",
            "crm_connection_id",
            "started_at",
        ),
    )


class CrmConflictRow(Base):
    __tablename__ = "crm_conflicts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    crm_connection_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    external_object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    crm_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    closeros_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "crm_connection_id",
            "external_object_type",
            "external_object_id",
            "field_key",
            "status",
        ),
        CheckConstraint(f"status IN ({_quoted(_CONFLICT_STATUS_VALUES)})", name="status"),
        CheckConstraint(
            f"resolution IS NULL OR resolution IN ({_quoted(_CONFLICT_RESOLUTION_VALUES)})",
            name="resolution",
        ),
        CheckConstraint("version >= 1", name="version"),
        Index(
            "ix_crm_conflicts_tenant_connection_status", "tenant_id", "crm_connection_id", "status"
        ),
    )
