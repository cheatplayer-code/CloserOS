"""Tests for observability router and structured logging."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from closeros.infrastructure.production_feature_capabilities import ProductionFeatureCapabilities
from closeros.infrastructure.structured_logging import SafeMetricsCollector, StructuredLogger
from closeros_api.observability_router import (
    DenyDiagnosticsAuthorizer,
    ProductionReadinessProbe,
    RuntimeReadinessProbe,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_safe_metrics_collector_snapshot() -> None:
    metrics = SafeMetricsCollector()
    metrics.increment("health_checks_total")
    metrics.set_gauge("queue_depth", 3)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["health_checks_total"] == 1
    assert snapshot["gauges"]["queue_depth"] == 3


def test_structured_logger_emits_json(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.INFO)
    logger = StructuredLogger(logging.getLogger("test-observability"), service_name="api")
    logger.info("health_checked", route="/health")
    assert '"event":"health_checked"' in caplog.text or '"event": "health_checked"' in caplog.text


def _session_factory(
    *,
    migration_revision: str | None = "c4e8a2b6d1f0",
    fail_query: bool = False,
) -> Any:
    class _Session:
        async def execute(self, statement: object) -> object:
            if fail_query:
                raise RuntimeError("database unavailable")
            sql = str(statement)
            if "alembic_version" in sql:

                class _Result:
                    def first(self) -> tuple[str] | None:
                        if migration_revision is None:
                            return None
                        return (migration_revision,)

                return _Result()

            class _PingResult:
                def first(self) -> None:
                    return None

            return _PingResult()

    @asynccontextmanager
    async def factory() -> AsyncIterator[_Session]:
        yield _Session()

    return factory


def test_observability_router_health_and_ready() -> None:
    app = FastAPI()
    app.include_router(router)
    probe = RuntimeReadinessProbe(session_factory=None)
    app.state.readiness_probe = probe
    app.state.diagnostics_authorizer = DenyDiagnosticsAuthorizer()

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["dependencies"]["database"] == "failed"


def test_observability_ready_returns_503_when_database_fails() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.readiness_probe = RuntimeReadinessProbe(
        session_factory=_session_factory(fail_query=True),
    )
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"database": "failed"},
    }


def test_production_readiness_reports_disabled_optional_features() -> None:
    capabilities = ProductionFeatureCapabilities(
        whatsapp_enabled=False,
        crm_enabled=False,
        notifications_enabled=False,
        media_scanning_enabled=False,
        external_ai_enabled=False,
    )
    probe = ProductionReadinessProbe(
        session_factory=_session_factory(),
        capabilities=capabilities,
        key_provider_configured=False,
    )

    async def exercise() -> None:
        result = await probe.check()
        assert result.ready is True
        assert result.dependencies["whatsapp"] == "disabled"
        assert result.dependencies["crm"] == "disabled"
        assert result.dependencies["smtp"] == "disabled"
        assert result.dependencies["scanner"] == "disabled"
        assert result.dependencies["external_ai"] == "disabled"
        assert result.dependencies["database"] == "ok"
        assert "kms" not in result.dependencies

    import asyncio

    asyncio.run(exercise())


def test_production_readiness_marks_enabled_missing_smtp_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_FROM_ADDRESS", raising=False)
    for name, value in {
        "KMS_BASE_URL": "https://kms.example.test",
        "KMS_API_TOKEN_REF": "env:KMS_API_TOKEN",
        "KMS_ACTIVE_KEY_VERSION": "v1",
        "KMS_KEY_VERSIONS": "v1",
    }.items():
        monkeypatch.setenv(name, value)

    capabilities = ProductionFeatureCapabilities(
        whatsapp_enabled=False,
        crm_enabled=False,
        notifications_enabled=True,
        media_scanning_enabled=False,
        external_ai_enabled=False,
    )
    probe = ProductionReadinessProbe(
        session_factory=_session_factory(),
        capabilities=capabilities,
        key_provider_configured=True,
    )

    async def exercise() -> None:
        result = await probe.check()
        assert result.ready is False
        assert result.dependencies["smtp"] == "failed"
        assert result.dependencies["whatsapp"] == "disabled"

    import asyncio

    asyncio.run(exercise())


def test_observability_diagnostics_requires_authorization() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.diagnostics_authorizer = DenyDiagnosticsAuthorizer()
    client = TestClient(app)
    response = client.get("/ops/diagnostics")
    assert response.status_code == 403


def test_observability_diagnostics_allows_authorized_request() -> None:
    class _AllowAuthorizer:
        async def authorize(self, request) -> bool:  # type: ignore[no-untyped-def]
            return True

    app = FastAPI()
    app.include_router(router)
    app.state.readiness_probe = RuntimeReadinessProbe(session_factory=None)
    app.state.diagnostics_authorizer = _AllowAuthorizer()
    client = TestClient(app)
    response = client.get("/ops/diagnostics")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "metrics" in response.json()


def test_observability_diagnostics_includes_safe_capabilities_matrix() -> None:
    class _AllowAuthorizer:
        async def authorize(self, request) -> bool:  # type: ignore[no-untyped-def]
            return True

    capabilities = ProductionFeatureCapabilities(
        whatsapp_enabled=True,
        crm_enabled=False,
        notifications_enabled=False,
        media_scanning_enabled=True,
        external_ai_enabled=False,
    )
    app = FastAPI()
    app.include_router(router)
    app.state.diagnostics_authorizer = _AllowAuthorizer()
    app.state.capabilities = capabilities
    client = TestClient(app)
    response = client.get("/ops/diagnostics")
    assert response.status_code == 200
    assert response.json()["capabilities"] == capabilities.as_safe_dict()


def test_production_readiness_uses_redis_ping_when_client_provided() -> None:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    capabilities = ProductionFeatureCapabilities(
        whatsapp_enabled=False,
        crm_enabled=False,
        notifications_enabled=False,
        media_scanning_enabled=False,
        external_ai_enabled=False,
    )
    probe = ProductionReadinessProbe(
        session_factory=_session_factory(),
        capabilities=capabilities,
        redis=redis,
        key_provider_configured=False,
    )

    async def exercise() -> None:
        result = await probe.check()
        assert result.dependencies["redis"] == "ok"
        redis.ping.assert_awaited_once()

    import asyncio

    asyncio.run(exercise())
