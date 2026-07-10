"""Smoke tests for the CLS-001 Python workspace."""

import closeros
from closeros_api import app
from closeros_worker import main as worker_main
from fastapi.testclient import TestClient


def test_shared_backend_package_imports() -> None:
    assert closeros.__version__ == "0.0.0"


def test_api_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_entry_point_exits_safely() -> None:
    assert worker_main() == 0
