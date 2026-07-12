"""Tests for database URL normalization and test-URL driver separation."""

# mypy: disable-error-code=import-untyped

import pytest
from closeros.infrastructure.database import (
    DatabaseConfigurationError,
    normalize_database_url,
)
from sqlalchemy import make_url

from tests.conftest import _admin_database_url, _rebuild_database_url

CI_TEST_DATABASE_URL = (
    "postgresql://closeros_ci:closeros_ci_only_not_production@127.0.0.1:5432/postgres"
)
SQLALCHEMY_INPUT_URL = (
    "postgresql+psycopg://closeros_ci:closeros_ci_only_not_production@127.0.0.1:5432/postgres"
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


def test_ci_test_database_url_produces_direct_admin_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", CI_TEST_DATABASE_URL)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    admin_url = _admin_database_url()

    assert admin_url.startswith("postgresql://")
    assert "+psycopg" not in admin_url
    assert admin_url.endswith("/postgres")
    assert "***" not in admin_url


def test_sqlalchemy_input_is_converted_for_direct_psycopg_use() -> None:
    direct = _rebuild_database_url(
        SQLALCHEMY_INPUT_URL,
        database="postgres",
        sqlalchemy=False,
    )

    parsed = make_url(direct)
    assert direct.startswith("postgresql://")
    assert "+psycopg" not in direct
    assert parsed.drivername == "postgresql"


def test_temporary_database_url_uses_sqlalchemy_driver() -> None:
    sqlalchemy_url = _rebuild_database_url(
        CI_TEST_DATABASE_URL,
        database="closeros_auth_test_abc123",
        sqlalchemy=True,
    )

    assert sqlalchemy_url.startswith("postgresql+psycopg://")
    assert sqlalchemy_url.endswith("/closeros_auth_test_abc123")


def test_database_name_replacement_preserves_connection_parts() -> None:
    rebuilt = _rebuild_database_url(
        SQLALCHEMY_INPUT_URL,
        database="closeros_auth_test_zzz999",
        sqlalchemy=False,
    )

    parsed = make_url(rebuilt)
    assert parsed.username == "closeros_ci"
    assert parsed.password == "closeros_ci_only_not_production"
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 5432
    assert parsed.database == "closeros_auth_test_zzz999"


def test_rebuilt_url_has_scheme_and_no_masked_password() -> None:
    rebuilt = _rebuild_database_url(
        CI_TEST_DATABASE_URL,
        database="postgres",
        sqlalchemy=False,
    )

    assert "://" in rebuilt
    assert not rebuilt.startswith("***")
    assert "***" not in rebuilt
    assert make_url(rebuilt).get_backend_name() == "postgresql"


def test_non_postgresql_url_is_rejected_by_rebuild() -> None:
    with pytest.raises(ValueError, match="only PostgreSQL"):
        _rebuild_database_url(
            "mysql://user:secret@127.0.0.1:3306/db", database="x", sqlalchemy=False
        )
