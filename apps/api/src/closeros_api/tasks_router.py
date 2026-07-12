"""Tenant follow-up task HTTP routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from closeros.application.follow_up_task_persistence import FollowUpTaskListFilter
from closeros.application.follow_up_task_service import FollowUpTaskServiceError
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.follow_up_task import FollowUpTask, FollowUpTaskPriority, FollowUpTaskStatus
from closeros.domain.identity import Role
from fastapi import APIRouter, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.product_schemas import (
    CreateFollowUpTaskRequest,
    FollowUpTaskListResponse,
    FollowUpTaskResponse,
    UpdateFollowUpTaskRequest,
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

router = APIRouter(tags=["tasks"])

_TASK_READ_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN, Role.MANAGER})
_TASK_WRITE_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})


def _task_response(task: FollowUpTask) -> FollowUpTaskResponse:
    return FollowUpTaskResponse(
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


@router.get("/tenants/{tenant_id}/tasks", response_model=FollowUpTaskListResponse)
async def list_tasks(
    request: Request,
    response: Response,
    tenant_id: UUID,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    assigned_membership_id: Annotated[UUID | None, Query()] = None,
    conversation_thread_id: Annotated[UUID | None, Query()] = None,
    overdue_only: Annotated[bool, Query()] = False,
) -> FollowUpTaskListResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_TASK_READ_ROLES,
    )
    if runtime.follow_up_task_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    status_value = FollowUpTaskStatus(status_filter) if status_filter is not None else None
    if Role.MANAGER in context.membership.roles and not context.membership.roles.intersection(
        {Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN}
    ):
        assigned_membership_id = context.membership.id
    page = await runtime.follow_up_task_service.list_tasks(
        filters=FollowUpTaskListFilter(
            tenant_id=tenant_id,
            status=status_value,
            assigned_membership_id=assigned_membership_id,
            conversation_thread_id=conversation_thread_id,
            overdue_only=overdue_only,
            now=runtime.clock.now(),
        ),
        limit=limit,
        cursor=decode_cursor(cursor),
    )
    apply_security_headers(response)
    return FollowUpTaskListResponse(
        tasks=[_task_response(task) for task in page.items],
        next_cursor=None if page.next_cursor is None else encode_cursor(page.next_cursor),
    )


@router.get("/tenants/{tenant_id}/tasks/{task_id}", response_model=FollowUpTaskResponse)
async def get_task(
    request: Request,
    response: Response,
    tenant_id: UUID,
    task_id: UUID,
) -> FollowUpTaskResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_TASK_READ_ROLES,
    )
    if runtime.follow_up_task_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    task = await runtime.follow_up_task_service.get_task(tenant_id=tenant_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable")
    if (
        Role.MANAGER in context.membership.roles
        and not context.membership.roles.intersection(
            {Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN}
        )
        and task.assigned_membership_id != context.membership.id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)
    apply_security_headers(response)
    return _task_response(task)


@router.post(
    "/tenants/{tenant_id}/tasks",
    response_model=FollowUpTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    request: Request,
    response: Response,
    tenant_id: UUID,
    payload: CreateFollowUpTaskRequest,
) -> FollowUpTaskResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_TASK_WRITE_ROLES,
    )
    if runtime.follow_up_task_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    try:
        task = await runtime.follow_up_task_service.create_task(
            tenant_id=tenant_id,
            conversation_thread_id=payload.conversation_thread_id,
            title=payload.title,
            priority=FollowUpTaskPriority(payload.priority),
            assigned_membership_id=payload.assigned_membership_id,
            source_finding_id=payload.source_finding_id,
            due_at=payload.due_at,
            created_by_user_id=context.user.id,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except FollowUpTaskServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="request unavailable"
        ) from error
    apply_security_headers(response)
    return _task_response(task)


@router.patch("/tenants/{tenant_id}/tasks/{task_id}", response_model=FollowUpTaskResponse)
async def update_task(
    request: Request,
    response: Response,
    tenant_id: UUID,
    task_id: UUID,
    payload: UpdateFollowUpTaskRequest,
) -> FollowUpTaskResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_TASK_READ_ROLES,
    )
    if runtime.follow_up_task_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    service = runtime.follow_up_task_service
    audit = audit_context_from_request(request)
    actor_type = AuditActorType.USER
    actor_id = context.user.id
    try:
        if payload.action == "start":
            task = await service.mutate_status(
                tenant_id=tenant_id,
                task_id=task_id,
                target_status=FollowUpTaskStatus.IN_PROGRESS,
                audit_action=AuditAction.FOLLOW_UP_TASK_STARTED,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.action == "complete":
            task = await service.mutate_status(
                tenant_id=tenant_id,
                task_id=task_id,
                target_status=FollowUpTaskStatus.COMPLETED,
                audit_action=AuditAction.FOLLOW_UP_TASK_COMPLETED,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.action == "cancel":
            task = await service.mutate_status(
                tenant_id=tenant_id,
                task_id=task_id,
                target_status=FollowUpTaskStatus.CANCELLED,
                audit_action=AuditAction.FOLLOW_UP_TASK_CANCELLED,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.action == "reopen":
            task = await service.mutate_status(
                tenant_id=tenant_id,
                task_id=task_id,
                target_status=FollowUpTaskStatus.OPEN,
                audit_action=AuditAction.FOLLOW_UP_TASK_REOPENED,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.assigned_membership_id is not None or payload.action == "assign":
            task = await service.assign(
                tenant_id=tenant_id,
                task_id=task_id,
                assigned_membership_id=payload.assigned_membership_id,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.priority is not None:
            task = await service.change_priority(
                tenant_id=tenant_id,
                task_id=task_id,
                priority=FollowUpTaskPriority(payload.priority),
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        elif payload.due_at is not None or payload.action == "reschedule":
            task = await service.change_due_date(
                tenant_id=tenant_id,
                task_id=task_id,
                due_at=payload.due_at,
                expected_version=payload.version,
                audit_context=audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="validation failed"
            )
    except FollowUpTaskServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="request unavailable"
        ) from error
    apply_security_headers(response)
    return _task_response(task)
