"""Migration tests for V1 integrity foundation revision a1c3e5f7b9d0."""

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
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _sqlalchemy_database_url,
)

V1_REVISION = "a1c3e5f7b9d0"
PRE_V1_REVISION = "c4e8a2b6d1f0"
HEAD_REVISION = "c3e5a7b9d1f0"


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_v1_integrity_{uuid.uuid4().hex[:12]}"
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


def test_v1_integrity_revision_chains_from_xy() -> None:
    config = build_alembic_config("postgresql+psycopg://local:local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(V1_REVISION)
    assert revision is not None
    assert revision.down_revision == PRE_V1_REVISION
    assert script.get_current_head() == HEAD_REVISION


@pytest.mark.hi_persistence
def test_v1_integrity_upgrade_downgrade_reupgrade() -> None:
    with _isolated_database(revision=V1_REVISION) as (_a, _n, database_url, engine):
        inspector = inspect(engine)
        assert "synthetic_seed_manifests" in inspector.get_table_names()
        fks = inspector.get_foreign_keys("manager_assignments")
        assert any(
            fk.get("referred_table") == "memberships"
            and fk.get("constrained_columns") == ["tenant_id", "manager_user_id"]
            for fk in fks
        )
        config = build_alembic_config(database_url)
        command.downgrade(config, PRE_V1_REVISION)
        inspector = inspect(engine)
        assert "synthetic_seed_manifests" not in inspector.get_table_names()
        command.upgrade(config, V1_REVISION)
        inspector = inspect(engine)
        assert "synthetic_seed_resources" in inspector.get_table_names()
