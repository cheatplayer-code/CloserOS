"""Observability HTTP routes for health, readiness, and protected diagnostics."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, cast

from alembic.script import ScriptDirectory
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.infrastructure.alembic_config import build_alembic_config
from closeros.infrastructure.production_feature_capabilities import (
    ProductionFeatureCapabilities,
)
from closeros.infrastructure.structured_logging import SafeMetricsCollector
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.exceptions import HTTPException

router = APIRouter(tags=["observability"])

ACCESS_DENIED = "access denied"
DependencyStatus = Literal["ok", "failed", "disabled", "configured"]
_EXPECTED_MIGRATION_HEAD = "c4e8a2b6d1f0"


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    ready: bool
    dependencies: dict[str, str]


class ReadinessProbe(Protocol):
    async def check(self) -> ReadinessResult: ...

    async def check_database(self) -> bool: ...


def _migration_heads() -> frozenset[str]:
    config = build_alembic_config(
        "postgresql+psycopg://{user}:{password}@{host}:{port}/{database}".format(
            user="local",
            password="local",
            host="127.0.0.1",
            port=5432,
            database="local",
        )
    )
    script = ScriptDirectory.from_config(config)
    return frozenset(script.get_heads())


def _env_present(*names: str) -> bool:
    return all(os.environ.get(name, "").strip() for name in names)


class RuntimeReadinessProbe:
    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[Any]] | None,
    ) -> None:
        self._session_factory = session_factory

    async def check_database(self) -> bool:
        if self._session_factory is None:
            return False
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def check(self) -> ReadinessResult:
        database_ok = await self.check_database()
        database_status: DependencyStatus = "ok" if database_ok else "failed"
        return ReadinessResult(
            ready=database_ok,
            dependencies={"database": database_status},
        )


class ProductionReadinessProbe:
    """Production readiness checks for mandatory deps and enabled optional features."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractAsyncContextManager[Any]] | None,
        capabilities: ProductionFeatureCapabilities,
        redis: Redis | None = None,
        adapter_registry: ProviderAdapterRegistry | None = None,
        key_provider_configured: bool = False,
        expected_migration_heads: frozenset[str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._capabilities = capabilities
        self._redis = redis
        self._adapter_registry = adapter_registry
        self._key_provider_configured = key_provider_configured
        self._expected_migration_heads = expected_migration_heads or _migration_heads()

    async def check_database(self) -> bool:
        return (await self._check_database_and_migration()) == "ok"

    async def check(self) -> ReadinessResult:
        dependencies: dict[str, str] = {}
        ready = True

        database_status = await self._check_database_and_migration()
        dependencies["database"] = database_status
        if database_status == "failed":
            ready = False

        if self._redis is not None:
            redis_status = await self._check_redis()
            dependencies["redis"] = redis_status
            if redis_status == "failed":
                ready = False

        if self._key_provider_configured:
            kms_status = self._check_kms_config()
            dependencies["kms"] = kms_status
            if kms_status == "failed":
                ready = False

        if self._capabilities.notifications_enabled:
            smtp_status = self._check_smtp_config()
            dependencies["smtp"] = smtp_status
            if smtp_status == "failed":
                ready = False
        else:
            dependencies["smtp"] = "disabled"

        if self._capabilities.media_scanning_enabled:
            scanner_status = self._check_scanner_config()
            dependencies["scanner"] = scanner_status
            if scanner_status == "failed":
                ready = False
        else:
            dependencies["scanner"] = "disabled"

        if self._capabilities.whatsapp_enabled:
            whatsapp_status = self._check_whatsapp()
            dependencies["whatsapp"] = whatsapp_status
            if whatsapp_status == "failed":
                ready = False
        else:
            dependencies["whatsapp"] = "disabled"

        if self._capabilities.crm_enabled:
            crm_status = self._check_crm_config()
            dependencies["crm"] = crm_status
            if crm_status == "failed":
                ready = False
        else:
            dependencies["crm"] = "disabled"

        if self._capabilities.external_ai_enabled:
            ai_status = self._check_external_ai_config()
            dependencies["external_ai"] = ai_status
            if ai_status == "failed":
                ready = False
        else:
            dependencies["external_ai"] = "disabled"

        return ReadinessResult(ready=ready, dependencies=dependencies)

    async def _check_database_and_migration(self) -> DependencyStatus:
        if self._session_factory is None:
            return "failed"
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
                result = await session.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = result.first()
                current = row[0] if row else None
                if current is None:
                    return "failed"
                if current in self._expected_migration_heads:
                    return "ok"
                if current == _EXPECTED_MIGRATION_HEAD:
                    return "ok"
                return "failed"
        except Exception:
            return "failed"

    async def _check_redis(self) -> DependencyStatus:
        if self._redis is None:
            return "failed"
        try:
            pong = await self._redis.ping()
            return "ok" if pong else "failed"
        except Exception:
            return "failed"

    def _check_kms_config(self) -> DependencyStatus:
        if _env_present(
            "KMS_BASE_URL",
            "KMS_API_TOKEN_REF",
            "KMS_ACTIVE_KEY_VERSION",
            "KMS_KEY_VERSIONS",
        ):
            return "configured"
        return "failed"

    def _check_smtp_config(self) -> DependencyStatus:
        return "ok" if _env_present("SMTP_HOST", "SMTP_PORT", "SMTP_FROM_ADDRESS") else "failed"

    def _check_scanner_config(self) -> DependencyStatus:
        return "ok" if _env_present("CLAMAV_HOST", "CLAMAV_PORT") else "failed"

    def _check_whatsapp(self) -> DependencyStatus:
        registry_ready = (
            self._adapter_registry is not None
            and len(self._adapter_registry.registered_kinds()) > 0
        )
        secret_ref_ready = bool(os.environ.get("WHATSAPP_APP_SECRET_REF", "").strip())
        return "ok" if registry_ready or secret_ref_ready else "failed"

    def _check_crm_config(self) -> DependencyStatus:
        return (
            "ok"
            if _env_present("BITRIX24_PORTAL_DOMAIN", "BITRIX24_ACCESS_TOKEN_REF")
            else "failed"
        )

    def _check_external_ai_config(self) -> DependencyStatus:
        if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
            return "failed"
        if not (
            os.environ.get("DEEPSEEK_MODEL", "").strip() or os.environ.get("AI_MODEL", "").strip()
        ):
            return "failed"
        return "ok"


class DenyDiagnosticsAuthorizer:
    async def authorize(self, request: Request) -> bool:
        return False


class DiagnosticsAuthorizer(Protocol):
    async def authorize(self, request: Request) -> bool: ...


def _metrics(request: Request) -> SafeMetricsCollector:
    collector = getattr(request.app.state, "metrics_collector", None)
    if collector is None:
        collector = SafeMetricsCollector()
        request.app.state.metrics_collector = collector
    return cast(SafeMetricsCollector, collector)


def _readiness_probe(request: Request) -> ReadinessProbe:
    probe = getattr(request.app.state, "readiness_probe", None)
    if probe is None:
        session_factory = getattr(getattr(request.app.state, "auth", None), "session_factory", None)
        probe = RuntimeReadinessProbe(
            cast("Callable[[], AbstractAsyncContextManager[Any]] | None", session_factory),
        )
        request.app.state.readiness_probe = probe
    return cast(ReadinessProbe, probe)


def _diagnostics_authorizer(request: Request) -> DiagnosticsAuthorizer:
    authorizer = getattr(request.app.state, "diagnostics_authorizer", None)
    if authorizer is None:
        authorizer = DenyDiagnosticsAuthorizer()
        request.app.state.diagnostics_authorizer = authorizer
    return cast(DiagnosticsAuthorizer, authorizer)


MetricsDep = Annotated[SafeMetricsCollector, Depends(_metrics)]
ReadinessDep = Annotated[ReadinessProbe, Depends(_readiness_probe)]
AuthorizerDep = Annotated[DiagnosticsAuthorizer, Depends(_diagnostics_authorizer)]


def build_readiness_response(result: ReadinessResult) -> JSONResponse:
    content: dict[str, object] = {
        "status": "ready" if result.ready else "not_ready",
    }
    if result.dependencies:
        content["dependencies"] = result.dependencies
    status_code = status.HTTP_200_OK if result.ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=content)


@router.get("/health")
def health(metrics: MetricsDep) -> dict[str, str]:
    metrics.increment("health_checks_total")
    return {"status": "ok"}


@router.get("/ready")
async def ready(metrics: MetricsDep, probe: ReadinessDep) -> JSONResponse:
    metrics.increment("readiness_checks_total")
    return build_readiness_response(await probe.check())


@router.get("/ops/diagnostics")
async def diagnostics(
    request: Request,
    metrics: MetricsDep,
    authorizer: AuthorizerDep,
) -> JSONResponse:
    if not await authorizer.authorize(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)

    metrics.increment("diagnostics_requests_total")
    content: dict[str, object] = {
        "status": "ok",
        "metrics": metrics.snapshot(),
    }
    capabilities = getattr(request.app.state, "capabilities", None)
    if capabilities is not None and hasattr(capabilities, "as_safe_dict"):
        content["capabilities"] = capabilities.as_safe_dict()
    return JSONResponse(content=content)


__all__ = [
    "ProductionReadinessProbe",
    "ReadinessProbe",
    "ReadinessResult",
    "RuntimeReadinessProbe",
    "build_readiness_response",
    "router",
]
