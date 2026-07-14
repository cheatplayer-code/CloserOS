"""SQLAlchemy ORM models for product catalog persistence (Block V1-2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from closeros.infrastructure.orm_base import Base

_ENTITY_STATUS = ("draft", "active", "inactive", "archived")
_VERIFICATION = ("live", "verified", "synced", "stale", "unverified")
_PRICE_KIND = ("list", "sale", "promotional")
_SOURCE_KIND = ("manual", "csv_import", "system_seed")
_IMPORT_STATUS = (
    "uploaded",
    "validating",
    "validation_failed",
    "ready_to_publish",
    "publishing",
    "completed",
    "failed",
    "cancelled",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class CatalogSourceRow(Base):
    __tablename__ = "catalog_sources"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "source_code"),
        CheckConstraint(f"kind IN ({_quoted(_SOURCE_KIND)})", name="kind"),
        Index("ix_catalog_sources_tenant_updated_at", "tenant_id", "updated_at"),
    )


class CatalogProductRow(Base):
    __tablename__ = "catalog_products"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    category_code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "sku"),
        CheckConstraint(f"status IN ({_quoted(_ENTITY_STATUS)})", name="status"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_catalog_products_tenant_category_status",
            "tenant_id",
            "category_code",
            "status",
        ),
        Index("ix_catalog_products_tenant_sku", "tenant_id", "sku"),
        Index("ix_catalog_products_tenant_name_normalized", "tenant_id", "name_normalized"),
    )


class CatalogProductVariantRow(Base):
    __tablename__ = "catalog_product_variants"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "sku"),
        ForeignKeyConstraint(
            ("tenant_id", "product_id"),
            ("catalog_products.tenant_id", "catalog_products.id"),
        ),
        CheckConstraint(f"status IN ({_quoted(_ENTITY_STATUS)})", name="status"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_catalog_product_variants_tenant_product", "tenant_id", "product_id"),
        Index("ix_catalog_product_variants_tenant_sku", "tenant_id", "sku"),
    )


class CatalogProductPriceRow(Base):
    __tablename__ = "catalog_product_prices"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    source_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ("tenant_id", "variant_id"),
            ("catalog_product_variants.tenant_id", "catalog_product_variants.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_id"),
            ("catalog_sources.tenant_id", "catalog_sources.id"),
        ),
        CheckConstraint("amount_minor > 0", name="amount_minor_positive"),
        CheckConstraint(f"price_kind IN ({_quoted(_PRICE_KIND)})", name="price_kind"),
        CheckConstraint(
            f"verification_status IN ({_quoted(_VERIFICATION)})", name="verification_status"
        ),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="valid_window"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_catalog_product_prices_tenant_variant_valid",
            "tenant_id",
            "variant_id",
            "valid_from",
        ),
        Index(
            "ix_catalog_product_prices_tenant_source_updated",
            "tenant_id",
            "source_updated_at",
        ),
    )


class CatalogInventoryLevelRow(Base):
    __tablename__ = "catalog_inventory_levels"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    location_code: Mapped[str] = mapped_column(String(64), nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "variant_id", "location_code"),
        ForeignKeyConstraint(
            ("tenant_id", "variant_id"),
            ("catalog_product_variants.tenant_id", "catalog_product_variants.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_id"),
            ("catalog_sources.tenant_id", "catalog_sources.id"),
        ),
        CheckConstraint("available_quantity >= 0", name="available_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        CheckConstraint(
            "reserved_quantity <= available_quantity", name="reserved_not_exceed_available"
        ),
        CheckConstraint(
            f"verification_status IN ({_quoted(_VERIFICATION)})", name="verification_status"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_catalog_inventory_levels_tenant_variant",
            "tenant_id",
            "variant_id",
        ),
        Index(
            "ix_catalog_inventory_levels_tenant_source_updated",
            "tenant_id",
            "source_updated_at",
        ),
    )


class CatalogDeliveryFactRow(Base):
    __tablename__ = "catalog_delivery_facts"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    location_code: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_time_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "variant_id", "location_code"),
        ForeignKeyConstraint(
            ("tenant_id", "variant_id"),
            ("catalog_product_variants.tenant_id", "catalog_product_variants.id"),
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_id"),
            ("catalog_sources.tenant_id", "catalog_sources.id"),
        ),
        CheckConstraint("lead_time_hours >= 0", name="lead_time_non_negative"),
        CheckConstraint(
            f"verification_status IN ({_quoted(_VERIFICATION)})", name="verification_status"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class CatalogCommercialPolicyRow(Base):
    __tablename__ = "catalog_commercial_policies"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    allow_discount: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_discount_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    allow_hold_inventory: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        CheckConstraint(
            "max_discount_basis_points >= 0 AND max_discount_basis_points <= 10000",
            name="discount_bps_range",
        ),
        CheckConstraint("char_length(default_currency) = 3", name="currency_length"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class CatalogFreshnessPolicyRow(Base):
    __tablename__ = "catalog_freshness_policies"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    inventory_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    price_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    promotion_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    description_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        CheckConstraint("inventory_ttl_seconds >= 1", name="inventory_ttl_positive"),
        CheckConstraint("price_ttl_seconds >= 1", name="price_ttl_positive"),
        CheckConstraint("delivery_ttl_seconds >= 1", name="delivery_ttl_positive"),
        CheckConstraint("promotion_ttl_seconds >= 1", name="promotion_ttl_positive"),
        CheckConstraint("description_ttl_seconds >= 1", name="description_ttl_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class CatalogImportRunRow(Base):
    __tablename__ = "catalog_import_runs"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    creator_user_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    delimiter: Mapped[str] = mapped_column(String(1), nullable=False)
    payload_sha256: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ("tenant_id", "source_id"),
            ("catalog_sources.tenant_id", "catalog_sources.id"),
        ),
        CheckConstraint(f"status IN ({_quoted(_IMPORT_STATUS)})", name="status"),
        CheckConstraint("octet_length(payload_sha256) = 32", name="payload_sha256_length"),
        CheckConstraint("payload_bytes >= 0", name="payload_bytes_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_catalog_import_runs_tenant_created", "tenant_id", "created_at"),
    )


class CatalogImportRowResultRow(Base):
    __tablename__ = "catalog_import_row_results"

    id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    import_run_id: Mapped[uuid.UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "import_run_id", "row_number"),
        ForeignKeyConstraint(
            ("tenant_id", "import_run_id"),
            ("catalog_import_runs.tenant_id", "catalog_import_runs.id"),
        ),
        CheckConstraint("row_number >= 1", name="row_number_positive"),
        Index(
            "ix_catalog_import_row_results_tenant_run",
            "tenant_id",
            "import_run_id",
        ),
    )
