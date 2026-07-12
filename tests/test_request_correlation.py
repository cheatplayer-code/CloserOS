"""Tests for server-generated request correlation identifiers."""

from __future__ import annotations

from uuid import UUID

from closeros_api.app import create_app
from closeros_api.request_correlation import REQUEST_CORRELATION_HEADER
from fastapi.testclient import TestClient

from tests.auth_api_support import development_api_settings

_PLACEHOLDER_DATABASE_URL = (
    "postgresql+psycopg://closeros_local:closeros_local_only_change_me@127.0.0.1:5432/postgres"
)


def test_health_response_includes_generated_request_id() -> None:
    client = TestClient(
        create_app(settings=development_api_settings(database_url=_PLACEHOLDER_DATABASE_URL))
    )
    response = client.get("/health")
    header_value = response.headers.get(REQUEST_CORRELATION_HEADER)
    assert header_value is not None
    UUID(header_value)


def test_validation_error_includes_request_id() -> None:
    client = TestClient(
        create_app(settings=development_api_settings(database_url=_PLACEHOLDER_DATABASE_URL))
    )
    response = client.post("/api/v1/auth/register", json={})
    assert response.status_code == 422
    assert REQUEST_CORRELATION_HEADER in response.headers
