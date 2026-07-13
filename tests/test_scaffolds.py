"""Smoke tests for the CLS-001 Python workspace."""

import sys
from unittest.mock import patch

import closeros
import pytest
from closeros_api.app import create_app
from closeros_worker import main as worker_main
from fastapi.testclient import TestClient

from tests.auth_api_support import development_api_settings
from tests.database_url_support import placeholder_database_url


def test_shared_backend_package_imports() -> None:
    assert closeros.__version__ == "0.0.0"


def test_api_health_endpoint() -> None:
    app = create_app(settings=development_api_settings(database_url=placeholder_database_url()))
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_cli_help_exits_zero() -> None:
    with (
        patch.object(sys, "argv", ["closeros-worker", "--help"]),
        pytest.raises(SystemExit) as exc,
    ):
        worker_main()
    assert exc.value.code == 0
