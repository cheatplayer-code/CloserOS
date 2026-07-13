"""Tenant-scoped retention and legal hold HTTP routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.retention_purge_service import (
    RetentionPurgeService,
    RetentionPurgeUnavailableError,
)
from closeros.domain.identity import Role
from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers
from closeros_api.composition import ApiRuntime
from closeros_api.product_security import (
    REQUEST_UNAVAILABLE,
    require_tenant_context,
    runtime_from_request,
)

router = APIRouter(tags=["retention"])

_PRIVILEGED_RETENTION_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


class LegalHoldRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=128)
    reason_detail: str | None = Field(default=None, max_length=2048)


class LegalHoldResponse(BaseModel):
    id: UUID
    status: str
    reason_code: str


class RetentionDryRunResponse(BaseModel):
    items_scanned: int
    dry_run: bool = True


class RetentionPurgeAcceptedResponse(BaseModel):
    purge_run_id: UUID


class RetentionPurgeStatusResponse(BaseModel):
    id: UUID
    status: str
    dry_run: bool
    items_scanned: int
    items_deleted: int
    items_skipped_legal_hold: int


def _runtime(request: Request) -> ApiRuntime:
    return runtime_from_request(request)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


def _legal_hold_service(runtime: ApiRuntime) -> LegalHoldService:
    service = getattr(runtime, "legal_hold_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    return cast(LegalHoldService, service)


def _retention_purge_service(runtime: ApiRuntime) -> RetentionPurgeService:
    service = getattr(runtime, "retention_purge_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    return cast(RetentionPurgeService, service)


@router.post("/tenants/{tenant_id}/retention/dry-run", response_model=RetentionDryRunResponse)
async def retention_dry_run(
    tenant_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    expires_before: Annotated[datetime, Query()],
) -> RetentionDryRunResponse:
    await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_PRIVILEGED_RETENTION_ROLES,
    )

    purge_service = _retention_purge_service(runtime)
    result = await purge_service.dry_run(
        tenant_id=tenant_id,
        expires_before=expires_before,
        requested_at=datetime.now(UTC),
    )
    apply_security_headers(response)
    return RetentionDryRunResponse(items_scanned=result.items_scanned)


@router.post("/tenants/{tenant_id}/retention/purge", response_model=RetentionPurgeAcceptedResponse)
async def retention_purge(
    tenant_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    expires_before: Annotated[datetime, Query()],
) -> RetentionPurgeAcceptedResponse:
    await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_PRIVILEGED_RETENTION_ROLES,
    )

    purge_service = _retention_purge_service(runtime)
    try:
        purge_run_id = await purge_service.schedule_purge(
            tenant_id=tenant_id,
            expires_before=expires_before,
            requested_at=datetime.now(UTC),
        )
    except RetentionPurgeUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="retention purge unavailable",
        ) from exc

    apply_security_headers(response)
    return RetentionPurgeAcceptedResponse(purge_run_id=purge_run_id)


@router.get(
    "/tenants/{tenant_id}/retention/purge/{purge_run_id}",
    response_model=RetentionPurgeStatusResponse,
)
async def retention_purge_status(
    tenant_id: UUID,
    purge_run_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> RetentionPurgeStatusResponse:
    await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_PRIVILEGED_RETENTION_ROLES,
    )

    purge_service = _retention_purge_service(runtime)
    purge_run = await purge_service.get_purge_run(
        tenant_id=tenant_id,
        purge_run_id=purge_run_id,
    )
    if purge_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="purge run not found")

    apply_security_headers(response)
    return RetentionPurgeStatusResponse(
        id=purge_run.id,
        status=purge_run.status.value,
        dry_run=purge_run.dry_run,
        items_scanned=purge_run.items_scanned,
        items_deleted=purge_run.items_deleted,
        items_skipped_legal_hold=purge_run.items_skipped_legal_hold,
    )


@router.post("/tenants/{tenant_id}/legal-holds", response_model=LegalHoldResponse)
async def create_legal_hold(
    tenant_id: UUID,
    body: LegalHoldRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> LegalHoldResponse:
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_PRIVILEGED_RETENTION_ROLES,
    )

    legal_hold_service = _legal_hold_service(runtime)
    legal_hold = await legal_hold_service.create_hold(
        tenant_id=tenant_id,
        reason_code=body.reason_code,
        reason_detail=body.reason_detail,
        created_by_user_id=context.user.id,
        created_at=datetime.now(UTC),
    )
    apply_security_headers(response)
    return LegalHoldResponse(
        id=legal_hold.id,
        status=legal_hold.status.value,
        reason_code=legal_hold.reason_code,
    )


__all__ = ["router"]
