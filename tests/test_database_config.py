"""Tests for database URL normalization."""

# mypy: disable-error-code=import-untyped

import pytest
from closeros.infrastructure.database import (
    DatabaseConfigurationError,
    normalize_database_url,
)


def test_normalize_postgresql_url_to_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgresql://user:secret@127.0.0.1:5432/closeros_local")
        == "postgresql+psycopg://user:secret@127.0.0.1:5432/closeros_local"
    )


def test_normalize_postgres_alias() -> None:
    assert normalize_database_url(
        "postgres://user:secret@127.0.0.1:5432/closeros_local"
    ).startswith("postgresql+psycopg://")


def test_reject_non_postgresql_urls() -> None:
    with pytest.raises(DatabaseConfigurationError, match="only PostgreSQL"):
        normalize_database_url("sqlite:///tmp/test.db")
