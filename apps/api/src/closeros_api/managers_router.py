"""Tenant manager scorecard HTTP routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from closeros.application.scorecard_query_service import ManagerScorecard
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from fastapi import APIRouter, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers
from closeros_api.product_schemas import (
    FindingCountResponse,
    ManagerListItemResponse,
    ManagerListResponse,
    ManagerScorecardListResponse,
    ManagerScorecardResponse,
    ScorecardComponentsResponse,
)
from closeros_api.product_security import (
    ACCESS_DENIED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    require_tenant_context,
    runtime_from_request,
)

router = APIRouter(tags=["managers"])

_SCORECARD_READ_ROLES = frozenset(
    {Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN, Role.MANAGER}
)


def _scorecard_response(card: ManagerScorecard) -> ManagerScorecardResponse:
    return ManagerScorecardResponse(
        membership_id=card.membership_id,
        manager_user_id=card.manager_user_id,
        formula_version=card.formula_version,
        window_start=card.window_start,
        window_end=card.window_end,
        components=ScorecardComponentsResponse(
            response_rate_basis_points=card.components.response_rate_basis_points,
            conversion_rate_basis_points=card.components.conversion_rate_basis_points,
            finding_discipline_basis_points=card.components.finding_discipline_basis_points,
            task_completion_basis_points=card.components.task_completion_basis_points,
        ),
        composite_basis_points=card.composite_basis_points,
        composite_delta_basis_points=card.composite_delta_basis_points,
        finding_counts=[
            FindingCountResponse(
                finding_code=item.finding_code,
                severity=item.severity,
                count=item.count,
            )
            for item in card.finding_counts
        ],
        task_counts=card.task_counts,
    )


@router.get("/tenants/{tenant_id}/managers", response_model=ManagerListResponse)
async def list_managers(
    request: Request,
    response: Response,
    tenant_id: UUID,
) -> ManagerListResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_SCORECARD_READ_ROLES,
    )
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    uow = runtime.integrated_uow_factory()
    async with uow:
        memberships = await uow.memberships.list_for_tenant(tenant_id)
    managers = []
    for membership in memberships:
        if Role.MANAGER in membership.roles or Role.SALES_HEAD in membership.roles:
            if (
                Role.MANAGER in membership.roles
                and not context.membership.roles.intersection(
                    {Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN}
                )
                and membership.user_id != context.user.id
            ):
                continue
            managers.append(
                ManagerListItemResponse(
                    membership_id=membership.id,
                    manager_user_id=membership.user_id,
                    roles=sorted(role.value for role in membership.roles),
                )
            )
    apply_security_headers(response)
    return ManagerListResponse(managers=managers)


@router.get(
    "/tenants/{tenant_id}/managers/{membership_id}/scorecard",
    response_model=ManagerScorecardResponse,
)
async def get_manager_scorecard(
    request: Request,
    response: Response,
    tenant_id: UUID,
    membership_id: UUID,
    window_start: Annotated[datetime, Query()],
    window_end: Annotated[datetime, Query()],
) -> ManagerScorecardResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_SCORECARD_READ_ROLES,
    )
    if runtime.scorecard_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        card = await runtime.scorecard_query_service.get_scorecard(
            tenant_id=tenant_id,
            membership_id=membership_id,
            roles=context.membership.roles,
            actor_user_id=context.user.id,
            window_start=window_start,
            window_end=window_end,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable")
    apply_security_headers(response)
    return _scorecard_response(card)


@router.get("/tenants/{tenant_id}/scorecards", response_model=ManagerScorecardListResponse)
async def list_scorecards(
    request: Request,
    response: Response,
    tenant_id: UUID,
    window_start: Annotated[datetime, Query()],
    window_end: Annotated[datetime, Query()],
) -> ManagerScorecardListResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_SCORECARD_READ_ROLES,
    )
    if runtime.scorecard_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        cards = await runtime.scorecard_query_service.list_manager_scorecards(
            tenant_id=tenant_id,
            roles=context.membership.roles,
            actor_user_id=context.user.id,
            window_start=window_start,
            window_end=window_end,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    apply_security_headers(response)
    return ManagerScorecardListResponse(scorecards=[_scorecard_response(card) for card in cards])
