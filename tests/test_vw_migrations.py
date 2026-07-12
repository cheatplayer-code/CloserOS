"""PostgreSQL migration tests for VW WhatsApp Cloud provider schema."""

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
    database_name = f"closeros_vw_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_vw_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "b3d7f1a4c8e6"


def test_vw_migration_upgrade_creates_whatsapp_tables() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "whatsapp_cloud_connections" in table_names
        assert "outbound_messages" in table_names
        assert "provider_message_templates" in table_names
    finally:
        _drop_database(admin_url, database_name)


def test_vw_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "f6a8c2e4b1d3")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "whatsapp_cloud_connections" not in table_names
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            upgraded = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "whatsapp_cloud_connections" in upgraded
    finally:
        _drop_database(admin_url, database_name)
