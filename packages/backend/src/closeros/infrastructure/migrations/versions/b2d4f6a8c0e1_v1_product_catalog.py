"""Alembic revision: V1 product catalog grounding tables.

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d0
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f6a8c0e1"
down_revision: str | Sequence[str] | None = "a1c3e5f7b9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY = "('draft', 'active', 'inactive', 'archived')"
_VERIFY = "('live', 'verified', 'synced', 'stale', 'unverified')"
_PRICE = "('list', 'sale', 'promotional')"
_SOURCE = "('manual', 'csv_import', 'system_seed')"
_IMPORT = (
    "('uploaded', 'validating', 'validation_failed', 'ready_to_publish', "
    "'publishing', 'completed', 'failed', 'cancelled')"
)


def upgrade() -> None:
    op.create_table(
        "catalog_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_sources")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_catalog_sources_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "source_code", name=op.f("uq_catalog_sources_tenant_id_source_code")
        ),
        sa.CheckConstraint(f"kind IN {_SOURCE}", name=op.f("ck_catalog_sources_kind")),
    )
    op.create_index(
        op.f("ix_catalog_sources_tenant_updated_at"),
        "catalog_sources",
        ["tenant_id", "updated_at"],
    )

    op.create_table(
        "catalog_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_normalized", sa.String(length=200), nullable=False),
        sa.Column("category_code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_products")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_catalog_products_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "sku", name=op.f("uq_catalog_products_tenant_id_sku")),
        sa.CheckConstraint(f"status IN {_ENTITY}", name=op.f("ck_catalog_products_status")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_catalog_products_version_positive")),
    )
    op.create_index(
        op.f("ix_catalog_products_tenant_category_status"),
        "catalog_products",
        ["tenant_id", "category_code", "status"],
    )
    op.create_index(
        op.f("ix_catalog_products_tenant_sku"), "catalog_products", ["tenant_id", "sku"]
    )
    op.create_index(
        op.f("ix_catalog_products_tenant_name_normalized"),
        "catalog_products",
        ["tenant_id", "name_normalized"],
    )

    op.create_table(
        "catalog_product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["catalog_products.tenant_id", "catalog_products.id"],
            name=op.f("fk_catalog_product_variants_tenant_product"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_product_variants")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_catalog_product_variants_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id", "sku", name=op.f("uq_catalog_product_variants_tenant_id_sku")
        ),
        sa.CheckConstraint(f"status IN {_ENTITY}", name=op.f("ck_catalog_product_variants_status")),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_catalog_product_variants_version_positive")
        ),
    )
    op.create_index(
        op.f("ix_catalog_product_variants_tenant_product"),
        "catalog_product_variants",
        ["tenant_id", "product_id"],
    )
    op.create_index(
        op.f("ix_catalog_product_variants_tenant_sku"),
        "catalog_product_variants",
        ["tenant_id", "sku"],
    )

    op.create_table(
        "catalog_product_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("price_kind", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            name=op.f("fk_catalog_product_prices_tenant_variant"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["catalog_sources.tenant_id", "catalog_sources.id"],
            name=op.f("fk_catalog_product_prices_tenant_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_product_prices")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_catalog_product_prices_tenant_id_id")),
        sa.CheckConstraint(
            "amount_minor > 0", name=op.f("ck_catalog_product_prices_amount_minor_positive")
        ),
        sa.CheckConstraint(
            f"price_kind IN {_PRICE}", name=op.f("ck_catalog_product_prices_price_kind")
        ),
        sa.CheckConstraint(
            f"verification_status IN {_VERIFY}",
            name=op.f("ck_catalog_product_prices_verification_status"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name=op.f("ck_catalog_product_prices_valid_window"),
        ),
        sa.CheckConstraint(
            "char_length(currency) = 3", name=op.f("ck_catalog_product_prices_currency_length")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_catalog_product_prices_version_positive")),
    )
    op.create_index(
        op.f("ix_catalog_product_prices_tenant_variant_valid"),
        "catalog_product_prices",
        ["tenant_id", "variant_id", "valid_from"],
    )
    op.create_index(
        op.f("ix_catalog_product_prices_tenant_source_updated"),
        "catalog_product_prices",
        ["tenant_id", "source_updated_at"],
    )

    op.create_table(
        "catalog_inventory_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            name=op.f("fk_catalog_inventory_levels_tenant_variant"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["catalog_sources.tenant_id", "catalog_sources.id"],
            name=op.f("fk_catalog_inventory_levels_tenant_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_inventory_levels")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_catalog_inventory_levels_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "variant_id",
            "location_code",
            name=op.f("uq_catalog_inventory_levels_tenant_variant_location"),
        ),
        sa.CheckConstraint(
            "available_quantity >= 0",
            name=op.f("ck_catalog_inventory_levels_available_non_negative"),
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0",
            name=op.f("ck_catalog_inventory_levels_reserved_non_negative"),
        ),
        sa.CheckConstraint(
            "reserved_quantity <= available_quantity",
            name=op.f("ck_catalog_inventory_levels_reserved_not_exceed_available"),
        ),
        sa.CheckConstraint(
            f"verification_status IN {_VERIFY}",
            name=op.f("ck_catalog_inventory_levels_verification_status"),
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_catalog_inventory_levels_version_positive")
        ),
    )
    op.create_index(
        op.f("ix_catalog_inventory_levels_tenant_variant"),
        "catalog_inventory_levels",
        ["tenant_id", "variant_id"],
    )
    op.create_index(
        op.f("ix_catalog_inventory_levels_tenant_source_updated"),
        "catalog_inventory_levels",
        ["tenant_id", "source_updated_at"],
    )

    op.create_table(
        "catalog_delivery_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False),
        sa.Column("lead_time_hours", sa.Integer(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["catalog_product_variants.tenant_id", "catalog_product_variants.id"],
            name=op.f("fk_catalog_delivery_facts_tenant_variant"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["catalog_sources.tenant_id", "catalog_sources.id"],
            name=op.f("fk_catalog_delivery_facts_tenant_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_delivery_facts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_catalog_delivery_facts_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "variant_id",
            "location_code",
            name=op.f("uq_catalog_delivery_facts_tenant_variant_location"),
        ),
        sa.CheckConstraint(
            "lead_time_hours >= 0",
            name=op.f("ck_catalog_delivery_facts_lead_time_non_negative"),
        ),
        sa.CheckConstraint(
            f"verification_status IN {_VERIFY}",
            name=op.f("ck_catalog_delivery_facts_verification_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_catalog_delivery_facts_version_positive")),
    )

    op.create_table(
        "catalog_commercial_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allow_discount", sa.Boolean(), nullable=False),
        sa.Column("max_discount_basis_points", sa.Integer(), nullable=False),
        sa.Column("allow_hold_inventory", sa.Boolean(), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_commercial_policies")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_catalog_commercial_policies_tenant_id_id")
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_catalog_commercial_policies_tenant_id")),
        sa.CheckConstraint(
            "max_discount_basis_points >= 0 AND max_discount_basis_points <= 10000",
            name=op.f("ck_catalog_commercial_policies_discount_bps_range"),
        ),
        sa.CheckConstraint(
            "char_length(default_currency) = 3",
            name=op.f("ck_catalog_commercial_policies_currency_length"),
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_catalog_commercial_policies_version_positive")
        ),
    )

    op.create_table(
        "catalog_freshness_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("price_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("delivery_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("promotion_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("description_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_freshness_policies")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_catalog_freshness_policies_tenant_id_id")
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_catalog_freshness_policies_tenant_id")),
        sa.CheckConstraint(
            "inventory_ttl_seconds >= 1",
            name=op.f("ck_catalog_freshness_policies_inventory_ttl_positive"),
        ),
        sa.CheckConstraint(
            "price_ttl_seconds >= 1",
            name=op.f("ck_catalog_freshness_policies_price_ttl_positive"),
        ),
        sa.CheckConstraint(
            "delivery_ttl_seconds >= 1",
            name=op.f("ck_catalog_freshness_policies_delivery_ttl_positive"),
        ),
        sa.CheckConstraint(
            "promotion_ttl_seconds >= 1",
            name=op.f("ck_catalog_freshness_policies_promotion_ttl_positive"),
        ),
        sa.CheckConstraint(
            "description_ttl_seconds >= 1",
            name=op.f("ck_catalog_freshness_policies_description_ttl_positive"),
        ),
        sa.CheckConstraint(
            "version >= 1", name=op.f("ck_catalog_freshness_policies_version_positive")
        ),
    )

    op.create_table(
        "catalog_import_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creator_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delimiter", sa.String(length=1), nullable=False),
        sa.Column("payload_sha256", postgresql.BYTEA(), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=False),
        sa.Column("mapping_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("valid_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["catalog_sources.tenant_id", "catalog_sources.id"],
            name=op.f("fk_catalog_import_runs_tenant_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_import_runs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_catalog_import_runs_tenant_id_id")),
        sa.CheckConstraint(f"status IN {_IMPORT}", name=op.f("ck_catalog_import_runs_status")),
        sa.CheckConstraint(
            "octet_length(payload_sha256) = 32",
            name=op.f("ck_catalog_import_runs_payload_sha256_length"),
        ),
        sa.CheckConstraint(
            "payload_bytes >= 0", name=op.f("ck_catalog_import_runs_payload_bytes_non_negative")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_catalog_import_runs_version_positive")),
    )
    op.create_index(
        op.f("ix_catalog_import_runs_tenant_created"),
        "catalog_import_runs",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "catalog_import_row_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_row_key", sa.String(length=128), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=256), nullable=True),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "import_run_id"],
            ["catalog_import_runs.tenant_id", "catalog_import_runs.id"],
            name=op.f("fk_catalog_import_row_results_tenant_run"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_import_row_results")),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_catalog_import_row_results_tenant_id_id")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "import_run_id",
            "row_number",
            name=op.f("uq_catalog_import_row_results_tenant_run_row"),
        ),
        sa.CheckConstraint(
            "row_number >= 1", name=op.f("ck_catalog_import_row_results_row_number_positive")
        ),
    )
    op.create_index(
        op.f("ix_catalog_import_row_results_tenant_run"),
        "catalog_import_row_results",
        ["tenant_id", "import_run_id"],
    )


def downgrade() -> None:
    op.drop_table("catalog_import_row_results")
    op.drop_table("catalog_import_runs")
    op.drop_table("catalog_freshness_policies")
    op.drop_table("catalog_commercial_policies")
    op.drop_table("catalog_delivery_facts")
    op.drop_table("catalog_inventory_levels")
    op.drop_table("catalog_product_prices")
    op.drop_table("catalog_product_variants")
    op.drop_table("catalog_products")
    op.drop_table("catalog_sources")
