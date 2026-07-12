"""FastAPI application factory and default development entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from closeros_api.auth_router import router as auth_router
from closeros_api.auth_schemas import ErrorResponse, sanitize_validation_errors
from closeros_api.auth_security import apply_security_headers
from closeros_api.composition import ApiRuntimeOverrides, build_api_runtime
from closeros_api.request_correlation import RequestCorrelationMiddleware
from closeros_api.settings import ApiSettings
from closeros_api.tenants_router import router as tenants_router


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

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.auth_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Tenant-ID"],
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
        if runtime.session_factory is None:
            response = JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready"},
            )
        else:
            try:
                async with runtime.session_factory() as session:
                    await session.execute(text("SELECT 1"))
                response = JSONResponse(content={"status": "ready"})
            except Exception:
                response = JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "not_ready"},
                )
        apply_security_headers(response)
        return response

    application.include_router(auth_router, prefix="/api/v1/auth")
    application.include_router(tenants_router, prefix="/api/v1")
    return application


def _build_default_app() -> FastAPI:
    try:
        return create_app()
    except Exception:
        fallback = FastAPI(title="CloserOS API", version="0.0.0")

        @fallback.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        return fallback


app = _build_default_app()
