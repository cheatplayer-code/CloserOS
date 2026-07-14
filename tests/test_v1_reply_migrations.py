"""Migration tests for V1 reply memory revision c3e5a7b9d1f0."""

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

REPLY_REVISION = "c3e5a7b9d1f0"
PRE_REPLY_REVISION = "b2d4f6a8c0e1"


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_v1_reply_{uuid.uuid4().hex[:12]}"
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


def test_reply_revision_chains_from_catalog() -> None:
    config = build_alembic_config("postgresql+psycopg://local:local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(REPLY_REVISION)
    assert revision is not None
    assert revision.down_revision == PRE_REPLY_REVISION
    assert script.get_current_head() == REPLY_REVISION


@pytest.mark.hi_persistence
def test_reply_memory_upgrade_downgrade_reupgrade() -> None:
    with _isolated_database(revision=REPLY_REVISION) as (_a, _n, database_url, engine):
        inspector = inspect(engine)
        for table in (
            "reply_suggestion_runs",
            "reply_suggestion_candidates",
            "reply_suggestion_events",
            "buyer_memory_facts",
        ):
            assert table in inspector.get_table_names()

        config = build_alembic_config(database_url)
        command.downgrade(config, PRE_REPLY_REVISION)
        inspector = inspect(engine)
        for table in (
            "reply_suggestion_runs",
            "reply_suggestion_candidates",
            "reply_suggestion_events",
            "buyer_memory_facts",
        ):
            assert table not in inspector.get_table_names()

        command.upgrade(config, REPLY_REVISION)
        inspector = inspect(engine)
        assert "reply_suggestion_runs" in inspector.get_table_names()
        assert "buyer_memory_facts" in inspector.get_table_names()
