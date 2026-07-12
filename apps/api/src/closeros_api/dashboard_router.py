"""Tenant dashboard HTTP routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from fastapi import APIRouter, Query, Request, Response

from closeros_api.product_schemas import (
    DashboardMetricResponse,
    DashboardResponse,
    ManagerPerformanceResponse,
)
from closeros_api.product_security import (
    audit_context_from_request,
    require_tenant_context,
    runtime_from_request,
)

router = APIRouter(tags=["dashboard"])

_DASHBOARD_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


@router.get("/tenants/{tenant_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    request: Request,
    response: Response,
    tenant_id: UUID,
    window_start: Annotated[datetime, Query()],
    window_end: Annotated[datetime, Query()],
) -> DashboardResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_DASHBOARD_ROLES,
    )
    if runtime.dashboard_query_service is None:
        from starlette import status
        from starlette.exceptions import HTTPException

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="request unavailable"
        )
    summary = await runtime.dashboard_query_service.get_dashboard(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        audit_context=audit_context_from_request(request),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    from closeros_api.auth_security import apply_security_headers

    apply_security_headers(response)
    return DashboardResponse(
        formula_version=summary.formula_version,
        window_start=summary.window_start,
        window_end=summary.window_end,
        previous_window_start=summary.previous_window_start,
        previous_window_end=summary.previous_window_end,
        total_conversations=summary.total_conversations,
        open_high_severity_findings=summary.open_high_severity_findings,
        overdue_follow_up_tasks=summary.overdue_follow_up_tasks,
        metrics=[
            DashboardMetricResponse(
                key=item.key,
                current_value=item.current_value,
                previous_value=item.previous_value,
                delta=item.delta,
            )
            for item in summary.metrics
        ],
        manager_summaries=[
            ManagerPerformanceResponse(
                manager_user_id=item.manager_user_id,
                response_rate_basis_points=item.response_rate_basis_points,
                conversion_rate_basis_points=item.conversion_rate_basis_points,
                active_thread_count=item.active_thread_count,
            )
            for item in summary.manager_summaries
        ],
    )
