"""Tenant-scoped metrics HTTP routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.metrics_audit import metrics_viewed_event
from closeros.application.metrics_enqueue_service import MetricsEnqueueUnavailableError
from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from closeros.domain.metrics import MetricScope
from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import (
    CSRF_HEADER_NAME,
    apply_security_headers,
    csrf_token_is_valid,
    origin_is_allowed,
    read_session_cookie,
)
from closeros_api.composition import ApiRuntime
from closeros_api.metrics_schemas import (
    MetricsListResponse,
    MetricSnapshotResponse,
    MetricsRecalculateAcceptedResponse,
    MetricValueResponse,
)
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["metrics"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_UNAVAILABLE = "request unavailable"
_PRIVILEGED_METRICS_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


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


def _require_origin(request: Request, runtime: ApiRuntime) -> None:
    origin = request.headers.get("origin")
    if not origin_is_allowed(
        origin=origin,
        allowed_origins=runtime.settings.auth_allowed_origins,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _require_csrf(
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


async def _require_privileged_tenant_context(
    request: Request,
    runtime: ApiRuntime,
    *,
    tenant_id: UUID,
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
    except TenantAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error

    if not any(role in _PRIVILEGED_METRICS_ROLES for role in context.membership.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    return context


@router.get("/tenants/{tenant_id}/metrics", response_model=MetricsListResponse)
async def list_metrics(
    request: Request,
    runtime: RuntimeDep,
    tenant_id: UUID,
    scope: Annotated[MetricScope, Query()],
    manager_user_id: Annotated[UUID | None, Query()] = None,
    window_start: Annotated[datetime | None, Query()] = None,
    window_end: Annotated[datetime | None, Query()] = None,
    formula_version: Annotated[str | None, Query()] = None,
) -> MetricsListResponse:
    context = await _require_privileged_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
    )
    if scope is MetricScope.MANAGER and manager_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="validation failed"
        )

    snapshots = await runtime.metrics_query_service.list_snapshots(
        tenant_id=tenant_id,
        scope=scope,
        manager_user_id=manager_user_id,
        window_start=window_start,
        window_end=window_end,
        formula_version=formula_version,
    )
    if snapshots and runtime.integrated_uow_factory is not None:
        first = snapshots[0]
        uow = runtime.integrated_uow_factory()
        async with uow:
            await append_required_audit_event(
                uow.audit_events,
                metrics_viewed_event(
                    tenant_id=tenant_id,
                    metric_scope=scope.value,
                    formula_version=first.formula_version,
                    window_code=first.window.window_code,
                    occurred_at=runtime.clock.now(),
                    audit_context=_audit_context(request),
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=runtime.uuid_factory(),
                ),
            )
            await uow.commit()
    return MetricsListResponse(
        snapshots=[
            MetricSnapshotResponse(
                scope=snapshot.scope.value,
                manager_user_id=snapshot.manager_user_id,
                window_start=snapshot.window.start,
                window_end=snapshot.window.end,
                window_code=snapshot.window.window_code,
                formula_version=snapshot.formula_version,
                computed_at=snapshot.computed_at,
                values=[
                    MetricValueResponse(
                        key=value.key.value,
                        value=value.value,
                        numerator=value.numerator,
                        denominator=value.denominator,
                    )
                    for value in snapshot.values
                ],
            )
            for snapshot in snapshots
        ]
    )


@router.post(
    "/tenants/{tenant_id}/metrics/recalculate",
    response_model=MetricsRecalculateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_metrics_recalculation(
    request: Request,
    runtime: RuntimeDep,
    tenant_id: UUID,
) -> Response:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    _require_origin(request, runtime)
    _require_csrf(request, runtime, session_token)
    context = await _require_privileged_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
    )
    try:
        await runtime.metrics_enqueue_service.enqueue_tenant_recalculation(
            tenant_id=tenant_id,
            time_zone=context.tenant.time_zone,
            requested_at=runtime.clock.now(),
            audit_context=_audit_context(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except MetricsEnqueueUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        ) from error

    response = Response(
        content=MetricsRecalculateAcceptedResponse().model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_202_ACCEPTED,
    )
    apply_security_headers(response)
    return response
