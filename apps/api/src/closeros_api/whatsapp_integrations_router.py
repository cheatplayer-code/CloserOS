"""Tenant WhatsApp Cloud integration administration HTTP routes."""

from __future__ import annotations

from uuid import UUID

from closeros.application.whatsapp_connection_service import (
    WhatsAppConnectionServiceError,
)
from closeros.application.whatsapp_persistence import WhatsAppConnectionNotFoundError
from closeros.domain.audit import AuditActorType
from closeros.domain.identity import Role
from closeros.domain.whatsapp_cloud_connection import WhatsAppCloudConnection
from fastapi import APIRouter, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.product_security import (
    AUTHENTICATION_FAILED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    require_csrf,
    require_origin,
    require_tenant_context,
    runtime_from_request,
)
from closeros_api.whatsapp_schemas import (
    CreateWhatsAppConnectionRequest,
    UpdateWhatsAppConnectionRequest,
    WhatsAppConnectionActionRequest,
    WhatsAppConnectionListResponse,
    WhatsAppConnectionResponse,
)

router = APIRouter(tags=["whatsapp-integrations"])

_WHATSAPP_READ_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})
_WHATSAPP_WRITE_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


def _webhook_callback_path(connection: WhatsAppCloudConnection) -> str:
    return f"/api/v1/webhooks/whatsapp_cloud/{connection.webhook_public_key}"


def _connection_response(connection: WhatsAppCloudConnection) -> WhatsAppConnectionResponse:
    return WhatsAppConnectionResponse(
        id=connection.id,
        channel_connection_id=connection.channel_connection_id,
        provider=connection.provider.value,
        app_id=connection.app_id,
        waba_id=connection.waba_id,
        phone_number_id=connection.phone_number_id,
        display_phone_number=connection.display_phone_number,
        graph_api_version=connection.graph_api_version,
        access_token_ref=connection.access_token_ref,
        app_secret_ref=connection.app_secret_ref,
        verify_token_ref=connection.verify_token_ref,
        status=connection.status.value,
        webhook_subscription_status=connection.webhook_subscription_status.value,
        capabilities=[
            capability.value
            for capability in sorted(connection.capabilities, key=lambda item: item.value)
        ],
        webhook_public_key=connection.webhook_public_key,
        webhook_callback_path=_webhook_callback_path(connection),
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        last_verified_at=connection.last_verified_at,
        version=connection.version,
    )


@router.get(
    "/tenants/{tenant_id}/integrations/whatsapp",
    response_model=WhatsAppConnectionListResponse,
)
async def list_whatsapp_connections(
    request: Request,
    response: Response,
    tenant_id: UUID,
) -> WhatsAppConnectionListResponse:
    runtime = runtime_from_request(request)
    await require_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
        allowed_roles=_WHATSAPP_READ_ROLES,
    )
    if runtime.whatsapp_connection_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    connections = await runtime.whatsapp_connection_service.list_connections(
        tenant_id=tenant_id,
    )
    apply_security_headers(response)
    return WhatsAppConnectionListResponse(
        connections=[_connection_response(connection) for connection in connections],
    )


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp",
    response_model=WhatsAppConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_whatsapp_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    payload: CreateWhatsAppConnectionRequest,
) -> WhatsAppConnectionResponse:
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
        allowed_roles=_WHATSAPP_WRITE_ROLES,
    )
    if runtime.whatsapp_connection_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    channel_connection_id = runtime.uuid_factory()
    try:
        connection = await runtime.whatsapp_connection_service.create_connection(
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            app_id=payload.app_id,
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            display_phone_number=payload.display_phone_number,
            graph_api_version=payload.graph_api_version,
            access_token_ref=payload.access_token_ref,
            app_secret_ref=payload.app_secret_ref,
            verify_token_ref=payload.verify_token_ref,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except WhatsAppConnectionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)


@router.patch(
    "/tenants/{tenant_id}/integrations/whatsapp/{connection_id}",
    response_model=WhatsAppConnectionResponse,
)
async def update_whatsapp_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: UpdateWhatsAppConnectionRequest,
) -> WhatsAppConnectionResponse:
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
        allowed_roles=_WHATSAPP_WRITE_ROLES,
    )
    if runtime.whatsapp_connection_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        connection = await runtime.whatsapp_connection_service.update_connection(
            tenant_id=tenant_id,
            connection_id=connection_id,
            app_id=payload.app_id,
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            display_phone_number=payload.display_phone_number,
            graph_api_version=payload.graph_api_version,
            access_token_ref=payload.access_token_ref,
            app_secret_ref=payload.app_secret_ref,
            verify_token_ref=payload.verify_token_ref,
            expected_version=payload.version,
        )
    except WhatsAppConnectionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource unavailable",
        ) from error
    except WhatsAppConnectionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/{connection_id}/verify",
    response_model=WhatsAppConnectionResponse,
)
async def verify_whatsapp_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: WhatsAppConnectionActionRequest,
) -> WhatsAppConnectionResponse:
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
        allowed_roles=_WHATSAPP_WRITE_ROLES,
    )
    if runtime.whatsapp_connection_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        connection = await runtime.whatsapp_connection_service.verify_connection(
            tenant_id=tenant_id,
            connection_id=connection_id,
            expected_version=payload.version,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except WhatsAppConnectionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource unavailable",
        ) from error
    except WhatsAppConnectionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/{connection_id}/disable",
    response_model=WhatsAppConnectionResponse,
)
async def disable_whatsapp_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: WhatsAppConnectionActionRequest,
) -> WhatsAppConnectionResponse:
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
        allowed_roles=_WHATSAPP_WRITE_ROLES,
    )
    if runtime.whatsapp_connection_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        )
    try:
        connection = await runtime.whatsapp_connection_service.disable_connection(
            tenant_id=tenant_id,
            connection_id=connection_id,
            expected_version=payload.version,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except WhatsAppConnectionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource unavailable",
        ) from error
    except WhatsAppConnectionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request unavailable",
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)
