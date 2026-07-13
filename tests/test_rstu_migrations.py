"""PostgreSQL migration tests for RSTU product workspace schema."""

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
    database_name = f"closeros_rstu_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)
    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_rstu_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "c4e8a2b6d1f0"


def test_rstu_migration_upgrade_creates_follow_up_tasks() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "follow_up_tasks" in table_names
    finally:
        _drop_database(admin_url, database_name)


def test_rstu_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "e3b7c9d1f5a2")
        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "follow_up_tasks" not in table_names
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            upgraded = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert "follow_up_tasks" in upgraded
    finally:
        _drop_database(admin_url, database_name)
