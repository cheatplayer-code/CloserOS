"""PostgreSQL migration tests for the authentication schema."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import uuid

import psycopg
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.database import create_migration_engine
from sqlalchemy import inspect

from tests.conftest import (
    _admin_database_url,
    _create_database,
    _drop_database,
    _rebuild_database_url,
    _sqlalchemy_database_url,
)


def _create_isolated_database_url() -> tuple[str, str, str]:
    admin_url = _admin_database_url()
    database_name = f"closeros_auth_migration_{uuid.uuid4().hex[:12]}"
    _create_database(admin_url, database_name)

    database_url = _sqlalchemy_database_url(admin_url, database_name)
    return admin_url, database_name, database_url


def test_initial_migration_revision_is_head() -> None:
    config = build_alembic_config("postgresql+psycopg://local/local@127.0.0.1:5432/local")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "c3e5a7b9d1f0"


def test_migration_upgrade_creates_authentication_tables() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    try:
        command.upgrade(config, "head")
        engine = create_migration_engine(database_url)
        try:
            table_names = inspect(engine).get_table_names()
        finally:
            engine.dispose()

        assert {
            "users",
            "authentication_credentials",
            "authentication_sessions",
            "authentication_one_time_tokens",
        }.issubset(set(table_names))
    finally:
        _drop_database(admin_url, database_name)


def test_migration_downgrade_and_reupgrade() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")

        engine = create_migration_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        assert "users" not in table_names
        assert "authentication_credentials" not in table_names
        assert "authentication_sessions" not in table_names
        assert "authentication_one_time_tokens" not in table_names

        command.upgrade(config, "head")

        engine = create_migration_engine(database_url)
        try:
            upgraded_table_names = inspect(engine).get_table_names()
        finally:
            engine.dispose()

        assert "authentication_sessions" in upgraded_table_names
    finally:
        _drop_database(admin_url, database_name)


def test_session_database_constraint_rejects_invalid_stage_combination() -> None:
    admin_url, database_name, database_url = _create_isolated_database_url()
    config = build_alembic_config(database_url)

    try:
        command.upgrade(config, "head")

        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        direct_url = _rebuild_database_url(
            database_url,
            database=database_name,
            sqlalchemy=False,
        )
        with psycopg.connect(direct_url) as connection:
            connection.execute(
                "INSERT INTO users (id, status) VALUES (%s, %s)",
                (user_id, "active"),
            )
            connection.commit()
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO authentication_sessions (
                        id, user_id, token_hash, stage, assurance_level,
                        mfa_completed, created_at, last_seen_at, expires_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        TIMESTAMPTZ '2026-07-12T06:00:00Z',
                        TIMESTAMPTZ '2026-07-12T06:00:00Z',
                        TIMESTAMPTZ '2026-07-12T18:00:00Z'
                    )
                    """,
                    (
                        session_id,
                        user_id,
                        bytes(range(32)),
                        "pending_mfa",
                        "multi_factor",
                        True,
                    ),
                )
    finally:
        _drop_database(admin_url, database_name)
