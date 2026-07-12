"""Tenant analysis query HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.tenant_context import TenantContextUnavailableError
from closeros.domain.access import TenantAccessDeniedError
from closeros.domain.identity import Role
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.analysis_schemas import (
    AnalysisCitationResponse,
    AnalysisEvidenceResponse,
    AnalysisFindingResponse,
    AnalysisRunResponse,
    AnalysisRunsResponse,
)
from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.composition import ApiRuntime
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["analysis"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_UNAVAILABLE = "request unavailable"
_ALLOWED_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


async def _require_allowed_role(request: Request, runtime: ApiRuntime, *, tenant_id: UUID) -> None:
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
    if not any(role in _ALLOWED_ROLES for role in context.membership.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


@router.get("/tenants/{tenant_id}/analysis/runs", response_model=AnalysisRunsResponse)
async def list_analysis_runs(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    tenant_id: UUID,
    conversation_thread_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AnalysisRunsResponse:
    await _require_allowed_role(request, runtime, tenant_id=tenant_id)
    if runtime.analysis_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    runs = await runtime.analysis_query_service.list_runs(
        tenant_id=tenant_id,
        conversation_thread_id=conversation_thread_id,
        limit=limit,
    )
    payload = AnalysisRunsResponse(
        runs=[
            AnalysisRunResponse(
                id=run_view.run.id,
                conversation_thread_id=run_view.run.conversation_thread_id,
                status=run_view.run.status,
                prompt_version=run_view.run.prompt_version,
                rubric_version=run_view.run.rubric_version,
                model_provider=run_view.run.model_provider,
                requested_at=run_view.run.requested_at,
                completed_at=run_view.run.completed_at,
                failure_code=run_view.run.failure_code,
                findings=[
                    AnalysisFindingResponse(
                        id=finding_view.finding.id,
                        finding_code=finding_view.finding.finding_code,
                        severity=finding_view.finding.severity,
                        status=finding_view.finding.status,
                        confidence_basis_points=finding_view.finding.confidence_basis_points,
                        created_at=finding_view.finding.created_at,
                        evidence=[
                            AnalysisEvidenceResponse(message_id=item.message_id)
                            for item in finding_view.evidence
                        ],
                        citations=[
                            AnalysisCitationResponse(
                                chunk_id=item.chunk_id,
                                document_id=item.document_id,
                                document_version_id=item.document_version_id,
                                retrieval_rank=item.retrieval_rank,
                                relevance_basis_points=item.relevance_basis_points,
                            )
                            for item in finding_view.citations
                        ],
                    )
                    for finding_view in run_view.findings
                ],
            )
            for run_view in runs
        ]
    )
    apply_security_headers(response)
    return payload
