"""Tenant knowledge management HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from closeros.domain.knowledge import KnowledgeDocumentVersion
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.composition import ApiRuntime
from closeros_api.knowledge_schemas import (
    KnowledgeDocumentResponse,
    KnowledgeDocumentsResponse,
    KnowledgeUploadRequest,
    KnowledgeUploadResponse,
    KnowledgeVersionResponse,
)
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["knowledge"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_UNAVAILABLE = "request unavailable"
_MANAGE_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


async def _require_context(
    request: Request, runtime: ApiRuntime, *, tenant_id: UUID
) -> TenantContext:
    token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    try:
        return await runtime.tenant_context_resolver.resolve(
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


def _require_manage_role(context: TenantContext) -> None:
    if not any(role in _MANAGE_ROLES for role in context.membership.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _version_response(version: KnowledgeDocumentVersion) -> KnowledgeVersionResponse:
    return KnowledgeVersionResponse(
        id=version.id,
        version_number=version.version_number,
        status=version.status.value,
        created_at=version.created_at,
        approved_at=version.approved_at,
        indexed_at=version.indexed_at,
        revoked_at=version.effective_until,
    )


@router.get("/tenants/{tenant_id}/knowledge/documents", response_model=KnowledgeDocumentsResponse)
async def list_documents(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeDocumentsResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_manage_role(context)
    if runtime.knowledge_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    documents = await runtime.knowledge_service.list_documents(
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    payload = KnowledgeDocumentsResponse(
        documents=[
            KnowledgeDocumentResponse(
                id=item.document.id,
                source_type=item.document.source_type,
                source_code=item.document.external_reference,
                status=item.document.status,
                created_at=item.document.created_at,
                updated_at=item.document.updated_at,
                latest_version=None
                if item.latest_version is None
                else KnowledgeVersionResponse(
                    id=item.latest_version.id,
                    version_number=item.latest_version.version_number,
                    status=item.latest_version.status,
                    created_at=item.latest_version.created_at,
                    approved_at=item.latest_version.approved_at,
                    indexed_at=item.latest_version.indexed_at,
                    revoked_at=item.latest_version.revoked_at,
                ),
            )
            for item in documents
        ]
    )
    apply_security_headers(response)
    return payload


@router.post(
    "/tenants/{tenant_id}/knowledge/documents",
    response_model=KnowledgeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    payload: KnowledgeUploadRequest,
) -> KnowledgeUploadResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_manage_role(context)
    if runtime.knowledge_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    result = await runtime.knowledge_service.upload_document(
        tenant_id=tenant_id,
        source_code=payload.source_code,
        plaintext_text=payload.plaintext_text,
        occurred_at=runtime.clock.now(),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    apply_security_headers(response)
    return KnowledgeUploadResponse(
        document_id=result.document_id,
        version_id=result.version_id,
        version_number=result.version_number,
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/versions/{version_id}/approve",
    response_model=KnowledgeVersionResponse,
)
async def approve_version(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    version_id: UUID,
) -> KnowledgeVersionResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_manage_role(context)
    if runtime.knowledge_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    version = await runtime.knowledge_service.approve_version(
        tenant_id=tenant_id,
        version_id=version_id,
        occurred_at=runtime.clock.now(),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    apply_security_headers(response)
    return KnowledgeVersionResponse(
        id=version.id,
        version_number=version.version_number,
        status=version.status,
        created_at=version.created_at,
        approved_at=version.approved_at,
        indexed_at=version.indexed_at,
        revoked_at=version.revoked_at,
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/versions/{version_id}/revoke",
    response_model=KnowledgeVersionResponse,
)
async def revoke_version(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    version_id: UUID,
) -> KnowledgeVersionResponse:
    context = await _require_context(request, runtime, tenant_id=tenant_id)
    _require_manage_role(context)
    if runtime.knowledge_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    version = await runtime.knowledge_service.revoke_version(
        tenant_id=tenant_id,
        version_id=version_id,
        occurred_at=runtime.clock.now(),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    apply_security_headers(response)
    return KnowledgeVersionResponse(
        id=version.id,
        version_number=version.version_number,
        status=version.status,
        created_at=version.created_at,
        approved_at=version.approved_at,
        indexed_at=version.indexed_at,
        revoked_at=version.revoked_at,
    )
