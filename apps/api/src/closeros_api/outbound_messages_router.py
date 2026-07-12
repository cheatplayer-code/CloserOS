"""Tenant human-approved outbound messaging HTTP routes."""

from __future__ import annotations

import json
from uuid import UUID

from closeros.application.conversation_query_service import ConversationAccessDeniedError
from closeros.application.outbound_message_service import (
    OutboundMessageAccessDeniedError,
    OutboundMessageServiceError,
)
from closeros.application.outbound_persistence import OutboundMessageNotFoundError
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import ContentEncoding
from closeros.domain.identity import Role
from closeros.domain.outbound_message import OutboundMessage, OutboundMessageKind
from fastapi import APIRouter, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.product_security import (
    ACCESS_DENIED,
    AUTHENTICATION_FAILED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    require_csrf,
    require_origin,
    require_tenant_context,
    runtime_from_request,
)
from closeros_api.whatsapp_schemas import (
    CreateOutboundDraftRequest,
    OutboundMessageActionRequest,
    OutboundMessageResponse,
)

router = APIRouter(tags=["outbound-messages"])

_OUTBOUND_READ_ROLES = frozenset(
    {Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN, Role.MANAGER},
)
_OUTBOUND_WRITE_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.MANAGER})


def _outbound_response(message: OutboundMessage) -> OutboundMessageResponse:
    return OutboundMessageResponse(
        id=message.id,
        conversation_thread_id=message.conversation_thread_id,
        channel_connection_id=message.channel_connection_id,
        kind=message.kind.value,
        status=message.status.value,
        provider_template_id=message.provider_template_id,
        created_by_user_id=message.created_by_user_id,
        approved_by_user_id=message.approved_by_user_id,
        failure_code=message.failure_code,
        created_at=message.created_at,
        approved_at=message.approved_at,
        queued_at=message.queued_at,
        sent_at=message.sent_at,
        completed_at=message.completed_at,
        updated_at=message.updated_at,
        version=message.version,
    )


def _encode_draft_payload(
    *,
    kind: OutboundMessageKind,
    body_text: str | None,
    template_parameters: list[str] | None,
) -> tuple[bytes, ContentEncoding]:
    if kind is OutboundMessageKind.FREE_FORM_TEXT:
        if body_text is None or not body_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="validation failed",
            )
        return body_text.encode("utf-8"), ContentEncoding.UTF8

    payload = {"parameters": template_parameters or []}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8"), ContentEncoding.JSON


@router.post(
    "/tenants/{tenant_id}/conversations/{thread_id}/outbound-drafts",
    response_model=OutboundMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_outbound_draft(
    request: Request,
    response: Response,
    tenant_id: UUID,
    thread_id: UUID,
    payload: CreateOutboundDraftRequest,
) -> OutboundMessageResponse:
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
        allowed_roles=_OUTBOUND_WRITE_ROLES,
    )
    if runtime.outbound_message_service is None or runtime.conversation_query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )

    try:
        kind = OutboundMessageKind(payload.kind)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validation failed",
        ) from error

    if kind is OutboundMessageKind.APPROVED_TEMPLATE and payload.provider_template_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validation failed",
        )

    try:
        plaintext, encoding = _encode_draft_payload(
            kind=kind,
            body_text=payload.body_text,
            template_parameters=payload.template_parameters,
        )
    except HTTPException:
        raise

    audit = audit_context_from_request(request)
    try:
        conversation = await runtime.conversation_query_service.get_conversation_detail(
            tenant_id=tenant_id,
            conversation_id=thread_id,
            roles=frozenset(context.membership.roles),
            user_id=context.user.id,
            audit_context=audit,
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except ConversationAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error

    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable")

    try:
        message = await runtime.outbound_message_service.create_draft(
            tenant_id=tenant_id,
            conversation_thread_id=thread_id,
            channel_connection_id=conversation.thread.channel_connection_id,
            kind=kind,
            plaintext=plaintext,
            encoding=encoding,
            provider_template_id=payload.provider_template_id,
            created_by_user_id=context.user.id,
            actor_roles=frozenset(context.membership.roles),
            audit_context=audit,
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except OutboundMessageAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error
    except OutboundMessageServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error

    apply_security_headers(response)
    return _outbound_response(message)


@router.post(
    "/tenants/{tenant_id}/outbound-messages/{message_id}/approve",
    response_model=OutboundMessageResponse,
)
async def approve_outbound_message(
    request: Request,
    response: Response,
    tenant_id: UUID,
    message_id: UUID,
    payload: OutboundMessageActionRequest,
) -> OutboundMessageResponse:
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
        allowed_roles=_OUTBOUND_WRITE_ROLES,
    )
    if runtime.outbound_message_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        message = await runtime.outbound_message_service.approve_and_queue(
            tenant_id=tenant_id,
            message_id=message_id,
            approved_by_user_id=context.user.id,
            actor_roles=frozenset(context.membership.roles),
            expected_version=payload.version,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except OutboundMessageAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error
    except OutboundMessageNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable"
        ) from error
    except OutboundMessageServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error

    apply_security_headers(response)
    return _outbound_response(message)


@router.post(
    "/tenants/{tenant_id}/outbound-messages/{message_id}/cancel",
    response_model=OutboundMessageResponse,
)
async def cancel_outbound_message(
    request: Request,
    response: Response,
    tenant_id: UUID,
    message_id: UUID,
    payload: OutboundMessageActionRequest,
) -> OutboundMessageResponse:
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
        allowed_roles=_OUTBOUND_WRITE_ROLES,
    )
    if runtime.outbound_message_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        message = await runtime.outbound_message_service.cancel(
            tenant_id=tenant_id,
            message_id=message_id,
            actor_roles=frozenset(context.membership.roles),
            expected_version=payload.version,
        )
    except OutboundMessageAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error
    except OutboundMessageNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable"
        ) from error
    except OutboundMessageServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error

    apply_security_headers(response)
    return _outbound_response(message)


@router.get(
    "/tenants/{tenant_id}/outbound-messages/{message_id}",
    response_model=OutboundMessageResponse,
)
async def get_outbound_message_status(
    request: Request,
    response: Response,
    tenant_id: UUID,
    message_id: UUID,
) -> OutboundMessageResponse:
    runtime = runtime_from_request(request)
    context = await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_OUTBOUND_READ_ROLES,
    )
    if runtime.outbound_message_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        message = await runtime.outbound_message_service.get_message(
            tenant_id=tenant_id,
            message_id=message_id,
            actor_roles=frozenset(context.membership.roles),
            viewer_user_id=context.user.id,
        )
    except OutboundMessageAccessDeniedError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED) from error

    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable")

    apply_security_headers(response)
    return _outbound_response(message)
