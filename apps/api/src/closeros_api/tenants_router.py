"""Tenant HTTP routes."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from closeros.application.audit_persistence import AuditQueryCursor, AuditQueryFilter
from closeros.application.audit_queries import TenantAuditQueryDeniedError
from closeros.application.audit_recording import AuditContext
from closeros.application.authentication_workflows import AuthenticationWorkflowUnavailableError
from closeros.application.tenant_context import TenantContextUnavailableError
from closeros.domain.access import TENANT_ACCESS_DENIED_MESSAGE, TenantAccessDeniedError
from closeros.domain.audit import AuditEvent
from closeros.domain.authentication import AuthenticationSessionStage
from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import (
    apply_security_headers,
    client_ip,
    fingerprint_value,
    read_session_cookie,
)
from closeros_api.composition import ApiRuntime
from closeros_api.request_correlation import get_request_correlation_id
from closeros_api.tenant_schemas import (
    AuditEventResponse,
    AuditEventsPageResponse,
    TenantSummaryResponse,
)

router = APIRouter(tags=["tenants"])

AUTHENTICATION_FAILED = "authentication failed"
TENANT_ACCESS_DENIED = TENANT_ACCESS_DENIED_MESSAGE
RATE_LIMITED = "too many requests"
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


def _audit_context(request: Request) -> AuditContext:
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)
    return AuditContext(
        correlation_id=get_request_correlation_id(request),
        http_method=request.method,
        route_template=route_template if isinstance(route_template, str) else None,
    )


async def _enforce_rate_limit(
    runtime: ApiRuntime,
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    account_fingerprint: str | None = None,
) -> None:
    ip = client_ip(
        request,
        trust_forwarded_client_ip=runtime.settings.trust_forwarded_client_ip,
    )
    ip_key = fingerprint_value(
        secret=runtime.settings.auth_rate_limit_secret,
        value=ip,
    )
    key = ip_key if account_fingerprint is None else f"{ip_key}:{account_fingerprint}"
    decision = await runtime.rate_limiter.check(
        scope=scope,
        key=key,
        limit=limit,
        window_seconds=window_seconds,
    )
    if not decision.allowed:
        headers = {"Retry-After": str(decision.retry_after_seconds or window_seconds)}
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMITED,
            headers=headers,
        )


def _session_fingerprint(runtime: ApiRuntime, session_token: RawAuthenticationToken) -> str:
    return fingerprint_value(
        secret=runtime.settings.auth_rate_limit_secret,
        value=session_token.value,
    )


async def _require_authenticated_user_id(
    request: Request,
    runtime: ApiRuntime,
) -> UUID:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    try:
        resolved = await runtime.workflows.resolve_session(
            raw_token=session_token,
            now=runtime.clock.now(),
        )
    except AuthenticationWorkflowUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    if resolved.session.stage is not AuthenticationSessionStage.AUTHENTICATED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    return resolved.user.id


def _encode_audit_cursor(cursor: AuditQueryCursor) -> str:
    payload = f"{cursor.occurred_at.isoformat()}|{cursor.event_id}".encode("ascii")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_audit_cursor(value: str) -> AuditQueryCursor:
    padding = "=" * (-len(value) % 4)
    try:
        decoded = urlsafe_b64decode(f"{value}{padding}".encode("ascii")).decode("ascii")
        occurred_at_raw, event_id_raw = decoded.split("|", maxsplit=1)
        occurred_at = datetime.fromisoformat(occurred_at_raw)
        event_id = UUID(event_id_raw)
    except (TypeError, ValueError, UnicodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="validation failed",
        ) from error

    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="validation failed",
        )

    return AuditQueryCursor(occurred_at=occurred_at, event_id=event_id)


def _audit_event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        scope=event.scope.value,
        tenant_id=event.tenant_id,
        actor_type=event.actor.actor_type.value,
        actor_id=event.actor.actor_id,
        action=event.action.value,
        target_type=event.target.target_type.value,
        target_id=event.target.target_id,
        occurred_at=event.occurred_at,
        correlation_id=event.correlation_id,
    )


def _tenant_summary(tenant: object, membership: object) -> TenantSummaryResponse:
    from closeros.domain.membership import Membership
    from closeros.domain.tenant import Tenant

    resolved_tenant = cast(Tenant, tenant)
    resolved_membership = cast(Membership, membership)
    return TenantSummaryResponse(
        id=resolved_tenant.id,
        name=resolved_tenant.name,
        status=resolved_tenant.status.value,
        time_zone=resolved_tenant.time_zone,
        roles=sorted(role.value for role in resolved_membership.roles),
    )


@router.get("/tenants", response_model=list[TenantSummaryResponse])
async def list_tenants(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> list[TenantSummaryResponse]:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    await _enforce_rate_limit(
        runtime,
        request,
        scope="tenant_list",
        limit=60,
        window_seconds=60,
        account_fingerprint=_session_fingerprint(runtime, session_token),
    )

    user_id = await _require_authenticated_user_id(request, runtime)
    tenant_pairs = await runtime.tenant_listing_service.list_tenants_for_user(user_id=user_id)
    payload = [_tenant_summary(tenant, membership) for tenant, membership in tenant_pairs]
    apply_security_headers(response)
    return payload


@router.get(
    "/tenants/{tenant_id}/audit-events",
    response_model=AuditEventsPageResponse,
)
async def list_tenant_audit_events(
    tenant_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = _DEFAULT_PAGE_SIZE,
) -> AuditEventsPageResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    await _enforce_rate_limit(
        runtime,
        request,
        scope="tenant_audit_events",
        limit=30,
        window_seconds=60,
        account_fingerprint=_session_fingerprint(runtime, session_token),
    )

    try:
        tenant_context = await runtime.tenant_context_resolver.resolve(
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=TENANT_ACCESS_DENIED,
        ) from None

    decoded_cursor = _decode_audit_cursor(cursor) if cursor is not None else None

    try:
        page = await runtime.tenant_audit_query_service.query(
            tenant=tenant_context.tenant,
            user=tenant_context.user,
            membership=tenant_context.membership,
            query_filter=AuditQueryFilter(tenant_id=tenant_id),
            audit_context=_audit_context(request),
            occurred_at=runtime.clock.now(),
            cursor=decoded_cursor,
            page_size=page_size,
        )
    except TenantAuditQueryDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=TENANT_ACCESS_DENIED,
        ) from None

    payload = AuditEventsPageResponse(
        events=[_audit_event_response(event) for event in page.events],
        next_cursor=None if page.next_cursor is None else _encode_audit_cursor(page.next_cursor),
    )
    apply_security_headers(response)
    return payload
