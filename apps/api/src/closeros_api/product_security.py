"""Shared tenant product API security helpers."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from typing import cast
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.identity import Role
from closeros.infrastructure.cursor_pagination import KeysetCursor
from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import Request, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import (
    CSRF_HEADER_NAME,
    csrf_token_is_valid,
    origin_is_allowed,
    read_session_cookie,
)
from closeros_api.composition import ApiRuntime
from closeros_api.request_correlation import get_request_correlation_id

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_UNAVAILABLE = "request unavailable"


def audit_context_from_request(request: Request) -> AuditContext:
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)
    return AuditContext(
        correlation_id=get_request_correlation_id(request),
        http_method=request.method,
        route_template=route_template if isinstance(route_template, str) else None,
    )


def runtime_from_request(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


def require_origin(request: Request, runtime: ApiRuntime) -> None:
    origin = request.headers.get("origin")
    if not origin_is_allowed(
        origin=origin,
        allowed_origins=runtime.settings.auth_allowed_origins,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def require_csrf(
    request: Request,
    runtime: ApiRuntime,
    session_token: RawAuthenticationToken,
) -> None:
    provided = request.headers.get(CSRF_HEADER_NAME)
    if provided is None or not csrf_token_is_valid(
        session_token=session_token,
        secret=runtime.settings.auth_csrf_secret,
        provided_token=provided,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


async def require_tenant_context(
    request: Request,
    runtime: ApiRuntime,
    *,
    tenant_id: UUID,
    allowed_roles: frozenset[Role] | None = None,
) -> TenantContext:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    try:
        context = await runtime.tenant_context_resolver.resolve(
            raw_token=session_token,
            tenant_id=tenant_id,
            correlation_id=get_request_correlation_id(request),
            now=runtime.clock.now(),
        )
    except TenantContextUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None
    except TenantAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    if allowed_roles is not None and not any(
        role in allowed_roles for role in context.membership.roles
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    return context


def encode_cursor(cursor: KeysetCursor) -> str:
    payload = f"{cursor.occurred_at.isoformat()}|{cursor.row_id}"
    return urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(value: str | None) -> KeysetCursor | None:
    if value is None or not value.strip():
        return None
    try:
        decoded = urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
        occurred_raw, row_id_raw = decoded.split("|", 1)
        return KeysetCursor(
            occurred_at=datetime.fromisoformat(occurred_raw), row_id=UUID(row_id_raw)
        )
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validation failed",
        ) from None
