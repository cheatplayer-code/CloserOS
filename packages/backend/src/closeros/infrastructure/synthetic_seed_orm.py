"""SQLAlchemy ORM rows for synthetic seed provenance."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_RESET_STATES = ("active", "resetting", "reset")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class SyntheticSeedManifestRow(Base):
    __tablename__ = "synthetic_seed_manifests"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    seed_version: Mapped[str] = mapped_column(String(64), nullable=False)
    seed_run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reset_state: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(("tenant_id",), ("tenants.id",)),
        CheckConstraint(
            f"reset_state IN ({_quoted(_RESET_STATES)})",
            name="reset_state",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_synthetic_seed_manifests_tenant_id_id"),
        UniqueConstraint("tenant_id", "seed_run_id", name="tenant_id_seed_run_id"),
        Index(
            "ix_synthetic_seed_manifests_tenant_reset_state",
            "tenant_id",
            "reset_state",
        ),
    )


class SyntheticSeedResourceRow(Base):
    __tablename__ = "synthetic_seed_resources"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    manifest_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    deletion_order: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "manifest_id"),
            ("synthetic_seed_manifests.tenant_id", "synthetic_seed_manifests.id"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "manifest_id",
            "resource_type",
            "resource_id",
            name="tenant_manifest_type_resource",
        ),
        CheckConstraint("deletion_order >= 0", name="deletion_order_non_negative"),
        Index(
            "ix_synthetic_seed_resources_tenant_manifest_order",
            "tenant_id",
            "manifest_id",
            "deletion_order",
        ),
    )
