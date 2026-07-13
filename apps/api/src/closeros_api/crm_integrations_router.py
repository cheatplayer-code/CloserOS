"""Tenant CRM integration administration HTTP routes."""

from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID

from closeros.application.crm_connection_service import CrmConnectionServiceError
from closeros.application.crm_persistence import CrmConnectionNotFoundError, CrmFieldMappingRecord
from closeros.application.crm_sync_service import CrmSyncServiceError
from closeros.domain.audit import AuditActorType
from closeros.domain.crm_conflict import CrmConflictResolution, CrmConflictStatus
from closeros.domain.crm_field_mapping import CrmFieldMappingStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.identity import Role
from fastapi import APIRouter, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers, read_session_cookie
from closeros_api.crm_schemas import (
    CreateCrmConnectionRequest,
    CrmConflictListResponse,
    CrmConflictResolveRequest,
    CrmConflictResponse,
    CrmConnectionActionRequest,
    CrmConnectionListResponse,
    CrmConnectionResponse,
    CrmFieldMappingListResponse,
    CrmFieldMappingRequest,
    CrmFieldMappingResponse,
    CrmReconcileResponse,
    CrmSyncAttemptResponse,
    CrmSyncOnceResponse,
    CrmSyncStatusResponse,
    UpdateCrmConnectionRequest,
)
from closeros_api.product_security import (
    AUTHENTICATION_FAILED,
    REQUEST_UNAVAILABLE,
    audit_context_from_request,
    require_csrf,
    require_origin,
    require_tenant_context,
    runtime_from_request,
)

router = APIRouter(tags=["crm-integrations"])

_CRM_READ_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})
_CRM_WRITE_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


def _crm_service(request: Request) -> Any:
    service = getattr(runtime_from_request(request), "crm_connection_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    return service


def _sync_service(request: Request) -> Any:
    service = getattr(runtime_from_request(request), "crm_sync_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    return service


def _reconciliation_service(request: Request) -> Any:
    service = getattr(runtime_from_request(request), "crm_reconciliation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    return service


def _connection_response(connection: Any) -> CrmConnectionResponse:
    return CrmConnectionResponse(
        id=connection.id,
        provider=connection.provider.value,
        portal_domain=connection.portal_domain,
        client_id_ref=connection.client_id_ref,
        client_secret_ref=connection.client_secret_ref,
        access_token_ref=connection.access_token_ref,
        refresh_token_ref=connection.refresh_token_ref,
        status=connection.status.value,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        last_verified_at=connection.last_verified_at,
        last_successful_sync_at=connection.last_successful_sync_at,
        version=connection.version,
    )


@router.get("/tenants/{tenant_id}/integrations/crm", response_model=CrmConnectionListResponse)
async def list_crm_connections(
    request: Request,
    response: Response,
    tenant_id: UUID,
) -> CrmConnectionListResponse:
    await require_tenant_context(
        request,
        runtime_from_request(request),
        tenant_id=tenant_id,
        allowed_roles=_CRM_READ_ROLES,
    )
    service = _crm_service(request)
    connections = await service.list_connections(tenant_id=tenant_id)
    apply_security_headers(response)
    return CrmConnectionListResponse(
        connections=[_connection_response(connection) for connection in connections]
    )


@router.post(
    "/tenants/{tenant_id}/integrations/crm",
    response_model=CrmConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_crm_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    payload: CreateCrmConnectionRequest,
) -> CrmConnectionResponse:
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
        allowed_roles=_CRM_WRITE_ROLES,
    )
    service = _crm_service(request)
    try:
        connection = await service.create_connection(
            tenant_id=tenant_id,
            provider=CrmProviderCode(payload.provider),
            portal_domain=payload.portal_domain,
            client_id_ref=payload.client_id_ref,
            client_secret_ref=payload.client_secret_ref,
            access_token_ref=payload.access_token_ref,
            refresh_token_ref=payload.refresh_token_ref,
            audit_context=audit_context_from_request(request),
            actor_type=AuditActorType.USER,
            actor_id=context.user.id,
        )
    except CrmConnectionServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=REQUEST_UNAVAILABLE
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)


@router.patch(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}",
    response_model=CrmConnectionResponse,
)
async def update_crm_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: UpdateCrmConnectionRequest,
) -> CrmConnectionResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    await require_tenant_context(
        request, runtime, tenant_id=tenant_id, allowed_roles=_CRM_WRITE_ROLES
    )
    service = _crm_service(request)
    try:
        connection = await service.update_connection(
            tenant_id=tenant_id,
            connection_id=connection_id,
            portal_domain=payload.portal_domain,
            client_id_ref=payload.client_id_ref,
            client_secret_ref=payload.client_secret_ref,
            access_token_ref=payload.access_token_ref,
            refresh_token_ref=payload.refresh_token_ref,
            expected_version=payload.version,
        )
    except CrmConnectionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable"
        ) from error
    apply_security_headers(response)
    return _connection_response(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/verify",
    response_model=CrmConnectionResponse,
)
async def verify_crm_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: CrmConnectionActionRequest,
) -> CrmConnectionResponse:
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
        allowed_roles=_CRM_WRITE_ROLES,
    )
    service = _crm_service(request)
    connection = await service.verify_connection(
        tenant_id=tenant_id,
        connection_id=connection_id,
        expected_version=payload.version,
        audit_context=audit_context_from_request(request),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    apply_security_headers(response)
    return _connection_response(connection)


@router.post(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/disable",
    response_model=CrmConnectionResponse,
)
async def disable_crm_connection(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: CrmConnectionActionRequest,
) -> CrmConnectionResponse:
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
        allowed_roles=_CRM_WRITE_ROLES,
    )
    service = _crm_service(request)
    connection = await service.disable_connection(
        tenant_id=tenant_id,
        connection_id=connection_id,
        expected_version=payload.version,
        audit_context=audit_context_from_request(request),
        actor_type=AuditActorType.USER,
        actor_id=context.user.id,
    )
    apply_security_headers(response)
    return _connection_response(connection)


@router.get(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/field-mappings",
    response_model=CrmFieldMappingListResponse,
)
async def list_field_mappings(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
) -> CrmFieldMappingListResponse:
    runtime = runtime_from_request(request)
    await require_tenant_context(
        request, runtime, tenant_id=tenant_id, allowed_roles=_CRM_READ_ROLES
    )
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    async with runtime.integrated_uow_factory() as uow:
        records = await uow.crm_field_mappings.list_by_connection(
            tenant_id=tenant_id,
            crm_connection_id=connection_id,
        )
    apply_security_headers(response)
    return CrmFieldMappingListResponse(
        mappings=[
            CrmFieldMappingResponse(
                id=record.id,
                external_object_type=record.external_object_type,
                external_field_key=record.external_field_key,
                closeros_field=record.closeros_field,
                status=record.status.value,
                created_at=record.created_at,
                updated_at=record.updated_at,
                version=record.version,
            )
            for record in records
        ]
    )


@router.put(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/field-mappings",
    response_model=CrmFieldMappingResponse,
)
async def upsert_field_mapping(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: CrmFieldMappingRequest,
) -> CrmFieldMappingResponse:
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
        allowed_roles=_CRM_WRITE_ROLES,
    )
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    now = runtime.clock.now().astimezone(UTC)
    async with runtime.integrated_uow_factory() as uow:
        record = await uow.crm_field_mappings.upsert(
            record=CrmFieldMappingRecord(
                id=runtime.uuid_factory(),
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
                external_object_type=payload.external_object_type,
                external_field_key=payload.external_field_key,
                closeros_field=payload.closeros_field,
                status=CrmFieldMappingStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                confirmed_by_user_id=context.user.id,
                version=1,
            )
        )
        await uow.commit()
    apply_security_headers(response)
    return CrmFieldMappingResponse(
        id=record.id,
        external_object_type=record.external_object_type,
        external_field_key=record.external_field_key,
        closeros_field=record.closeros_field,
        status=record.status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=record.version,
    )


@router.get(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/conflicts",
    response_model=CrmConflictListResponse,
)
async def list_crm_conflicts(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
) -> CrmConflictListResponse:
    await require_tenant_context(
        request,
        runtime_from_request(request),
        tenant_id=tenant_id,
        allowed_roles=_CRM_READ_ROLES,
    )
    service = _sync_service(request)
    conflicts = await service.list_open_conflicts(
        tenant_id=tenant_id,
        connection_id=connection_id,
    )
    apply_security_headers(response)
    return CrmConflictListResponse(
        conflicts=[
            CrmConflictResponse(
                id=conflict.id,
                external_object_type=conflict.external_object_type,
                external_object_id=conflict.external_object_id,
                field_key=conflict.field_key,
                crm_value_hash=conflict.crm_value_hash,
                closeros_value_hash=conflict.closeros_value_hash,
                status=conflict.status.value,
                created_at=conflict.created_at,
                version=conflict.version,
            )
            for conflict in conflicts
        ]
    )


@router.post(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/sync-once",
    response_model=CrmSyncOnceResponse,
)
async def sync_crm_connection_once(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
    payload: CrmConnectionActionRequest,
) -> CrmSyncOnceResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    await require_tenant_context(
        request, runtime, tenant_id=tenant_id, allowed_roles=_CRM_WRITE_ROLES
    )
    _ = payload
    service = _sync_service(request)
    try:
        await service.sync_once(tenant_id=tenant_id, connection_id=connection_id)
    except CrmSyncServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        ) from error
    apply_security_headers(response)
    return CrmSyncOnceResponse(status="synced")


@router.get(
    "/tenants/{tenant_id}/integrations/crm/{connection_id}/sync-status",
    response_model=CrmSyncStatusResponse,
)
async def get_sync_status(
    request: Request,
    response: Response,
    tenant_id: UUID,
    connection_id: UUID,
) -> CrmSyncStatusResponse:
    await require_tenant_context(
        request,
        runtime_from_request(request),
        tenant_id=tenant_id,
        allowed_roles=_CRM_READ_ROLES,
    )
    service = _sync_service(request)
    attempts = await service.recent_attempts(tenant_id=tenant_id, connection_id=connection_id)
    apply_security_headers(response)
    return CrmSyncStatusResponse(
        attempts=[
            CrmSyncAttemptResponse(
                id=attempt.id,
                direction=attempt.direction.value,
                status=attempt.status.value,
                resource_type=attempt.resource_type,
                started_at=attempt.started_at,
                finished_at=attempt.finished_at,
                records_seen=attempt.records_seen,
                records_changed=attempt.records_changed,
                error_code=attempt.error_code,
            )
            for attempt in attempts
        ]
    )


@router.post(
    "/tenants/{tenant_id}/integrations/crm/reconcile-once",
    response_model=CrmReconcileResponse,
)
async def reconcile_once(
    request: Request,
    response: Response,
    tenant_id: UUID,
) -> CrmReconcileResponse:
    runtime = runtime_from_request(request)
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)
    require_origin(request, runtime)
    require_csrf(request, runtime, session_token)
    await require_tenant_context(
        request, runtime, tenant_id=tenant_id, allowed_roles=_CRM_WRITE_ROLES
    )
    service = _reconciliation_service(request)
    count = await service.reconcile_once(tenant_id=tenant_id)
    apply_security_headers(response)
    return CrmReconcileResponse(synced_connections=count)


@router.post("/tenants/{tenant_id}/integrations/crm/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    request: Request,
    response: Response,
    tenant_id: UUID,
    conflict_id: UUID,
    payload: CrmConflictResolveRequest,
) -> dict[str, str]:
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
        allowed_roles=_CRM_WRITE_ROLES,
    )
    if runtime.integrated_uow_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=REQUEST_UNAVAILABLE
        )
    now = runtime.clock.now().astimezone(UTC)
    async with runtime.integrated_uow_factory() as uow:
        current = await uow.crm_conflicts.get_by_id_for_update(
            tenant_id=tenant_id,
            conflict_id=conflict_id,
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="resource unavailable"
            )
        updated = current.__class__(
            id=current.id,
            tenant_id=current.tenant_id,
            crm_connection_id=current.crm_connection_id,
            external_object_type=current.external_object_type,
            external_object_id=current.external_object_id,
            field_key=current.field_key,
            crm_value_hash=current.crm_value_hash,
            closeros_value_hash=current.closeros_value_hash,
            status=CrmConflictStatus.RESOLVED,
            created_at=current.created_at,
            resolved_at=now,
            resolved_by_user_id=context.user.id,
            resolution=CrmConflictResolution(payload.resolution),
            version=current.version + 1,
        )
        await uow.crm_conflicts.update(record=updated, expected_version=payload.version)
        await uow.commit()
    apply_security_headers(response)
    return {"status": "resolved"}
