"""Runtime-composed synthetic database URLs for tests."""

from __future__ import annotations

_DB_SCHEME = "postgresql+psycopg"
_DB_USER = "closeros_local"
_DB_PASSWORD = "closeros_local_only_change_me"
_DB_HOST = "127.0.0.1"
_DB_PORT = 5432
_DB_NAME = "postgres"


def placeholder_database_url() -> str:
    authority = f"{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}"
    return f"{_DB_SCHEME}://{authority}/{_DB_NAME}"


def test_placeholder_database_url_is_composed_at_runtime() -> None:
    url = placeholder_database_url()
    assert url == (f"{_DB_SCHEME}://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}")
