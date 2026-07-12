"""Tenant conversation review HTTP routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from closeros.application.analysis_enqueue_service import AnalysisEnqueueUnavailableError
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from closeros.infrastructure.product_query_repositories import ConversationListFilter
from fastapi import APIRouter, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.product_schemas import (
    AcceptedResponse,
    AnalysisCitationResponse,
    AnalysisEvidenceResponse,
    AnalysisFindingResponse,
    AnalysisRunResponse,
    ConversationDetailResponse,
    ConversationListItemResponse,
    ConversationListResponse,
    FollowUpTaskResponse,
    TimelineMessageResponse,
)
from closeros_api.product_security import (
    ACCESS_DENIED,
    AUTHENTICATION_FAILED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    decode_cursor,
    encode_cursor,
    require_csrf,
    require_origin,
    require_tenant_context,
    runtime_from_request,
)

router = APIRouter(tags=["conversations"])

_CONVERSATION_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN, Role.MANAGER})
_ANALYSIS_REQUEST_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


@router.get("/tenants/{tenant_id}/conversations", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    response: Response,
    tenant_id: UUID,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    updated_after: Annotated[datetime | None, Query()] = None,
    updated_before: Annotated[datetime | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    manager_user_id: Annotated[UUID | None, Query()] = None,
    lifecycle_status: Annotated[str | None, Query()] = None,
    finding_code: Annotated[str | None, Query()] = None,
    finding_severity: Annotated[str | None, Query()] = None,
    has_unresolved_task: Annotated[bool | None, Query()] = None,
) -> ConversationListResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_CONVERSATION_ROLES,
    )
    if runtime.conversation_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        page = await runtime.conversation_query_service.list_conversations(
            tenant_id=tenant_id,
            roles=context.membership.roles,
            user_id=context.user.id,
            filters=ConversationListFilter(
                tenant_id=tenant_id,
                attribution_as_of=runtime.clock.now(),
                updated_after=updated_after,
                updated_before=updated_before,
                provider=provider,
                manager_user_id=manager_user_id,
                lifecycle_status=lifecycle_status,
                finding_code=finding_code,
                finding_severity=finding_severity,
                has_unresolved_task=has_unresolved_task,
            ),
            limit=limit,
            cursor=decode_cursor(cursor),
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    apply_security_headers(response)
    return ConversationListResponse(
        conversations=[
            ConversationListItemResponse(
                id=item.id,
                channel_connection_id=item.channel_connection_id,
                provider=item.provider,
                external_conversation_id=item.external_conversation_id,
                lifecycle_status=item.lifecycle_status,
                manager_user_id=item.manager_user_id,
                updated_at=item.updated_at,
                open_finding_count=item.open_finding_count,
                high_severity_finding_count=item.high_severity_finding_count,
                has_unresolved_task=item.has_unresolved_task,
            )
            for item in page.items
        ],
        next_cursor=None if page.next_cursor is None else encode_cursor(page.next_cursor),
    )


@router.get(
    "/tenants/{tenant_id}/conversations/{thread_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation_detail(
    request: Request,
    response: Response,
    tenant_id: UUID,
    thread_id: UUID,
) -> ConversationDetailResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_CONVERSATION_ROLES,
    )
    if runtime.conversation_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        detail = await runtime.conversation_query_service.get_conversation_detail(
            tenant_id=tenant_id,
            conversation_id=thread_id,
            roles=context.membership.roles,
            user_id=context.user.id,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from None
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable")
    thread = detail.thread
    apply_security_headers(response)
    return ConversationDetailResponse(
        id=thread.id,
        channel_connection_id=thread.channel_connection_id,
        external_conversation_id=thread.external_conversation_id,
        lifecycle_status=(
            None if thread.lifecycle_status is None else thread.lifecycle_status.value
        ),
        manager_user_id=detail.manager_user_id,
        updated_at=thread.updated_at,
        created_at=thread.created_at,
        messages=[
            TimelineMessageResponse(
                message_id=item.message_id,
                sender_type=item.sender_type,
                direction=item.direction,
                sent_at=item.sent_at,
                received_at=item.received_at,
                sanitized_text=item.sanitized_text,
                is_deleted=item.is_deleted,
            )
            for item in detail.messages
        ],
        analyses=[
            AnalysisRunResponse(
                id=run_view.run.id,
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
                            AnalysisEvidenceResponse(message_id=evidence_item.message_id)
                            for evidence_item in finding_view.evidence
                        ],
                        citations=[
                            AnalysisCitationResponse(
                                chunk_id=citation_item.chunk_id,
                                document_id=citation_item.document_id,
                                document_version_id=citation_item.document_version_id,
                                retrieval_rank=citation_item.retrieval_rank,
                                relevance_basis_points=citation_item.relevance_basis_points,
                            )
                            for citation_item in finding_view.citations
                        ],
                    )
                    for finding_view in run_view.findings
                ],
            )
            for run_view in detail.analyses
        ],
        tasks=[
            FollowUpTaskResponse(
                id=task.id,
                conversation_thread_id=task.conversation_thread_id,
                source_finding_id=task.source_finding_id,
                title=task.title,
                status=task.status.value,
                priority=task.priority.value,
                assigned_membership_id=task.assigned_membership_id,
                due_at=task.due_at,
                completed_at=task.completed_at,
                cancelled_at=task.cancelled_at,
                created_at=task.created_at,
                updated_at=task.updated_at,
                version=task.version,
            )
            for task in detail.tasks
        ],
    )


@router.post(
    "/tenants/{tenant_id}/threads/{thread_id}/analyses",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_thread_analysis(
    request: Request,
    response: Response,
    tenant_id: UUID,
    thread_id: UUID,
) -> AcceptedResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_ANALYSIS_REQUEST_ROLES,
    )
    if runtime.analysis_enqueue_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        await runtime.analysis_enqueue_service.enqueue_for_thread(
            tenant_id=tenant_id,
            thread_id=thread_id,
            requested_at=runtime.clock.now(),
        )
    except AnalysisEnqueueUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        ) from error
    apply_security_headers(response)
    return AcceptedResponse()
