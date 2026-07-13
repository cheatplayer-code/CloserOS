"""PostgreSQL migration tests for CSV import ingestion schema."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid

from alembic import command
from alembic.script import ScriptDirectory
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import create_migration_engine
from sqlalchemy import inspect

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _sqlalchemy_database_url,
)


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_jk_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_jk_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "c4e8a2b6d1f0"


def test_jk_migration_upgrade_creates_csv_tables() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert {"csv_import_batches", "csv_import_row_errors"}.issubset(table_names)
    finally:
        _drop_database(admin_url, database_name)


def test_jk_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "e7a1c3d5f9b2")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "csv_import_batches" not in table_names
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            upgraded = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "csv_import_batches" in upgraded
    finally:
        _drop_database(admin_url, database_name)
