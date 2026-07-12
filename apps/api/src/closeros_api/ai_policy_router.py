"""Tenant AI policy HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.identity import Role
from fastapi import APIRouter, Depends, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.ai_policy_schemas import AiPolicyResponse, AiPolicyUpdateRequest
from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.composition import ApiRuntime
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["ai-policy"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_UNAVAILABLE = "request unavailable"
_ALLOWED_POLICY_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


async def _require_tenant_context(
    request: Request,
    runtime: ApiRuntime,
    *,
    tenant_id: UUID,
) -> TenantContext:
    token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    try:
        context = await runtime.tenant_context_resolver.resolve(
            raw_token=token,
            tenant_id=tenant_id,
            correlation_id=get_request_correlation_id(request),
            now=runtime.clock.now(),
        )
    except TenantContextUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED
        ) from None
    except TenantAccessDeniedError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    if not any(role in _ALLOWED_POLICY_ROLES for role in context.membership.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    return context


@router.get("/tenants/{tenant_id}/ai-policy", response_model=AiPolicyResponse)
async def get_ai_policy(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
) -> AiPolicyResponse:
    await _require_tenant_context(request, runtime, tenant_id=tenant_id)
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    uow = runtime.integrated_uow_factory()
    async with uow:
        policy = await uow.tenant_ai_policies.get_by_tenant_id(tenant_id=tenant_id)
        await uow.rollback()
    if policy is None:
        payload = AiPolicyResponse(
            mode="off",
            prompt_version="nopq-prompt-v1",
            rubric_version="nopq-rubric-v1",
            minimum_confidence_basis_points=6000,
            daily_budget_limit_minor_units=0,
            monthly_budget_limit_minor_units=0,
            updated_at=runtime.clock.now(),
        )
    else:
        payload = AiPolicyResponse(
            mode=policy.mode,
            prompt_version=policy.prompt_version,
            rubric_version=policy.rubric_version,
            minimum_confidence_basis_points=policy.minimum_confidence_basis_points,
            daily_budget_limit_minor_units=policy.daily_budget_limit_minor_units,
            monthly_budget_limit_minor_units=policy.monthly_budget_limit_minor_units,
            updated_at=policy.updated_at,
        )
    apply_security_headers(response)
    return payload


@router.put("/tenants/{tenant_id}/ai-policy", response_model=AiPolicyResponse)
async def update_ai_policy(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    payload: AiPolicyUpdateRequest,
) -> AiPolicyResponse:
    await _require_tenant_context(request, runtime, tenant_id=tenant_id)
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    now = runtime.clock.now()
    uow = runtime.integrated_uow_factory()
    async with uow:
        current = await uow.tenant_ai_policies.get_by_tenant_id_for_update(tenant_id=tenant_id)
        record_id = runtime.uuid_factory() if current is None else current.id
        updated = await uow.tenant_ai_policies.upsert(
            record=__import__(
                "closeros.application.ai_policy_persistence",
                fromlist=["TenantAiPolicyRecord"],
            ).TenantAiPolicyRecord(
                id=record_id,
                tenant_id=tenant_id,
                mode=payload.mode,
                prompt_version=payload.prompt_version,
                rubric_version=payload.rubric_version,
                minimum_confidence_basis_points=payload.minimum_confidence_basis_points,
                daily_budget_limit_minor_units=payload.daily_budget_limit_minor_units,
                monthly_budget_limit_minor_units=payload.monthly_budget_limit_minor_units,
                created_at=now if current is None else current.created_at,
                updated_at=now,
            )
        )
        await uow.commit()
    result = AiPolicyResponse(
        mode=updated.mode,
        prompt_version=updated.prompt_version,
        rubric_version=updated.rubric_version,
        minimum_confidence_basis_points=updated.minimum_confidence_basis_points,
        daily_budget_limit_minor_units=updated.daily_budget_limit_minor_units,
        monthly_budget_limit_minor_units=updated.monthly_budget_limit_minor_units,
        updated_at=updated.updated_at,
    )
    apply_security_headers(response)
    return result
