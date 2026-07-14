"""FastAPI application factory and default development entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from closeros_api.ai_policy_router import router as ai_policy_router
from closeros_api.analysis_router import router as analysis_router
from closeros_api.auth_router import router as auth_router
from closeros_api.auth_schemas import ErrorResponse, sanitize_validation_errors
from closeros_api.auth_security import apply_security_headers
from closeros_api.composition import ApiRuntimeOverrides, build_api_runtime
from closeros_api.conversations_router import router as conversations_router
from closeros_api.crm_integrations_router import router as crm_integrations_router
from closeros_api.csv_imports_router import router as csv_imports_router
from closeros_api.dashboard_router import router as dashboard_router
from closeros_api.knowledge_router import router as knowledge_router
from closeros_api.managers_router import router as managers_router
from closeros_api.metrics_router import router as metrics_router
from closeros_api.observability_router import (
    RuntimeReadinessProbe,
    build_readiness_response,
)
from closeros_api.observability_router import (
    router as observability_router,
)
from closeros_api.outbound_messages_router import router as outbound_messages_router
from closeros_api.product_catalog_router import router as product_catalog_router
from closeros_api.reply_suggestion_router import router as reply_suggestion_router
from closeros_api.request_correlation import RequestCorrelationMiddleware
from closeros_api.retention_router import router as retention_router
from closeros_api.settings import ApiSettings
from closeros_api.tasks_router import router as tasks_router
from closeros_api.tenants_router import router as tenants_router
from closeros_api.webhooks_router import router as webhooks_router
from closeros_api.whatsapp_integrations_router import router as whatsapp_integrations_router


def create_app(
    *,
    settings: ApiSettings | None = None,
    overrides: ApiRuntimeOverrides | None = None,
) -> FastAPI:
    resolved_settings = settings or ApiSettings.from_env()
    runtime = build_api_runtime(resolved_settings, overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.auth = runtime
        app.state.capabilities = runtime.capabilities
        app.state.readiness_probe = runtime.readiness_probe or RuntimeReadinessProbe(
            session_factory=runtime.session_factory,
        )
        try:
            yield
        finally:
            await runtime.dispose()

    application = FastAPI(
        title="CloserOS API",
        version="0.0.0",
        lifespan=lifespan,
    )
    application.state.auth = runtime
    application.state.capabilities = runtime.capabilities
    application.state.readiness_probe = runtime.readiness_probe or RuntimeReadinessProbe(
        session_factory=runtime.session_factory,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.auth_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "X-Tenant-ID",
            "X-Lawful-Source-Confirmed",
        ],
    )
    application.add_middleware(RequestCorrelationMiddleware)

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        response = JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "message": "validation failed",
                "errors": sanitize_validation_errors(list(exc.errors())),
            },
        )
        apply_security_headers(response)
        return response

    @application.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message="internal error").model_dump(),
        )
        apply_security_headers(response)
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    async def ready() -> JSONResponse:
        probe = application.state.readiness_probe
        response = build_readiness_response(await probe.check())
        apply_security_headers(response)
        return response

    application.include_router(auth_router, prefix="/api/v1/auth")
    application.include_router(tenants_router, prefix="/api/v1")
    application.include_router(webhooks_router, prefix="/api/v1")
    application.include_router(csv_imports_router, prefix="/api/v1")
    application.include_router(metrics_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(conversations_router, prefix="/api/v1")
    application.include_router(managers_router, prefix="/api/v1")
    application.include_router(tasks_router, prefix="/api/v1")
    application.include_router(knowledge_router, prefix="/api/v1")
    application.include_router(product_catalog_router, prefix="/api/v1")
    application.include_router(reply_suggestion_router, prefix="/api/v1")
    application.include_router(analysis_router, prefix="/api/v1")
    application.include_router(ai_policy_router, prefix="/api/v1")
    application.include_router(whatsapp_integrations_router, prefix="/api/v1")
    application.include_router(outbound_messages_router, prefix="/api/v1")
    application.include_router(crm_integrations_router, prefix="/api/v1")
    application.include_router(retention_router, prefix="/api/v1")
    application.include_router(observability_router, prefix="/api/v1")
    return application


app = create_app()
