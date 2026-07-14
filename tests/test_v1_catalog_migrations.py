"""Migration tests for V1 product catalog revision b2d4f6a8c0e1."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import create_migration_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _sqlalchemy_database_url,
)

CATALOG_REVISION = "b2d4f6a8c0e1"
PRE_CATALOG_REVISION = "a1c3e5f7b9d0"


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_v1_catalog_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


@contextmanager
def _isolated_database(*, revision: str = "head") -> Iterator[tuple[str, str, str, Engine]]:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    command.upgrade(config, revision)
    engine = create_migration_engine(database_url)
    try:
        yield admin_url, database_name, database_url, engine
    finally:
        engine.dispose()
        _drop_database(admin_url, database_name)


def test_catalog_revision_chains_from_v1_integrity() -> None:
    config = build_alembic_config("postgresql+psycopg://local:local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(CATALOG_REVISION)
    assert revision is not None
    assert revision.down_revision == PRE_CATALOG_REVISION
    assert script.get_current_head() == "c3e5a7b9d1f0"


@pytest.mark.hi_persistence
def test_catalog_upgrade_downgrade_reupgrade() -> None:
    with _isolated_database(revision=CATALOG_REVISION) as (_a, _n, database_url, engine):
        inspector = inspect(engine)
        for table in (
            "catalog_sources",
            "catalog_products",
            "catalog_product_variants",
            "catalog_product_prices",
            "catalog_inventory_levels",
            "catalog_delivery_facts",
            "catalog_commercial_policies",
            "catalog_freshness_policies",
            "catalog_import_runs",
            "catalog_import_row_results",
        ):
            assert table in inspector.get_table_names()

        price_fks = inspector.get_foreign_keys("catalog_product_prices")
        assert any(
            fk.get("referred_table") == "catalog_product_variants"
            and fk.get("constrained_columns") == ["tenant_id", "variant_id"]
            for fk in price_fks
        )

        # Negative inventory rejected
        tenant_id = uuid.uuid4()
        source_id = uuid.uuid4()
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO catalog_sources
                    (id, tenant_id, source_code, kind, created_at, updated_at)
                    VALUES (:id, :tenant_id, 'manual', 'manual', NOW(), NOW())
                    """
                ),
                {"id": source_id, "tenant_id": tenant_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO catalog_products
                    (id, tenant_id, sku, name, name_normalized, category_code, description,
                     status, created_at, updated_at, version)
                    VALUES (:id, :tenant_id, 'SKU1', 'Sofa', 'sofa', 'corner_sofa', '',
                            'draft', NOW(), NOW(), 1)
                    """
                ),
                {"id": product_id, "tenant_id": tenant_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO catalog_product_variants
                    (id, tenant_id, product_id, sku, display_name, attributes, status,
                     created_at, updated_at, version)
                    VALUES (:id, :tenant_id, :product_id, 'SKU1-V1', 'Sofa Gray', '{}'::jsonb,
                            'draft', NOW(), NOW(), 1)
                    """
                ),
                {"id": variant_id, "tenant_id": tenant_id, "product_id": product_id},
            )
            with pytest.raises(DBAPIError):
                conn.execute(
                    text(
                        """
                        INSERT INTO catalog_inventory_levels
                        (id, tenant_id, variant_id, location_code, available_quantity,
                         reserved_quantity, source_id, source_updated_at, verification_status,
                         checked_at, created_at, updated_at, version)
                        VALUES (:id, :tenant_id, :variant_id, 'almaty', -1, 0, :source_id,
                                NOW(), 'live', NOW(), NOW(), NOW(), 1)
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "variant_id": variant_id,
                        "source_id": source_id,
                    },
                )

        config = build_alembic_config(database_url)
        command.downgrade(config, PRE_CATALOG_REVISION)
        inspector = inspect(engine)
        assert "catalog_products" not in inspector.get_table_names()
        command.upgrade(config, CATALOG_REVISION)
        inspector = inspect(engine)
        assert "catalog_products" in inspector.get_table_names()
