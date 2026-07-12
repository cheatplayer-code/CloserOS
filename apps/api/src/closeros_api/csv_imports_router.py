"""Tenant-scoped CSV import HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.csv_import_persistence import CsvImportRecordNotFoundError
from closeros.application.csv_import_service import (
    CsvImportServiceError,
    CsvImportUnavailableError,
    CsvImportValidationError,
)
from closeros.application.tenant_context import TenantContext, TenantContextUnavailableError
from closeros.domain.access import TENANT_ACCESS_DENIED_MESSAGE, TenantAccessDeniedError
from closeros.domain.audit import AuditActorType
from closeros.domain.csv_import import CsvColumnMapping, CsvDelimiter, CsvSourceEncoding
from closeros.domain.identity import Role
from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import APIRouter, Depends, Query, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import (
    CSRF_HEADER_NAME,
    apply_security_headers,
    csrf_token_is_valid,
    origin_is_allowed,
    read_session_cookie,
)
from closeros_api.composition import ApiRuntime
from closeros_api.csv_import_schemas import (
    CsvImportAcceptedResponse,
    CsvImportPreviewColumnResponse,
    CsvImportPreviewResponse,
    CsvImportRowErrorResponse,
    CsvImportStartRequest,
    CsvImportStartResponse,
    CsvImportStatusResponse,
)
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["csv-imports"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
VALIDATION_FAILED = "validation failed"
REQUEST_UNAVAILABLE = "request unavailable"
LAWFUL_SOURCE_HEADER = "X-Lawful-Source-Confirmed"
_PRIVILEGED_IMPORT_ROLES = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("API runtime is not configured")
    return cast(ApiRuntime, runtime)


RuntimeDep = Annotated[ApiRuntime, Depends(_runtime)]


def _audit_context(request: Request) -> AuditContext:
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)
    return AuditContext(
        correlation_id=get_request_correlation_id(request),
        http_method=request.method,
        route_template=route_template if isinstance(route_template, str) else None,
    )


def _require_origin(request: Request, runtime: ApiRuntime) -> None:
    origin = request.headers.get("origin")
    if not origin_is_allowed(
        origin=origin,
        allowed_origins=runtime.settings.auth_allowed_origins,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _require_csrf(
    request: Request,
    runtime: ApiRuntime,
    session_token: RawAuthenticationToken,
) -> None:
    provided = request.headers.get(CSRF_HEADER_NAME)
    if provided is None or not csrf_token_is_valid(
        session_token=session_token,
        secret=runtime.settings.auth_csrf_secret,
        provided_token=provided,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


async def _require_privileged_tenant_context(
    request: Request,
    runtime: ApiRuntime,
    *,
    tenant_id: UUID,
) -> tuple[RawAuthenticationToken, TenantContext]:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    _require_origin(request, runtime)
    _require_csrf(request, runtime, session_token)

    try:
        tenant_context = await runtime.tenant_context_resolver.resolve(
            raw_token=session_token,
            tenant_id=tenant_id,
            correlation_id=get_request_correlation_id(request),
            now=runtime.clock.now(),
        )
    except TenantContextUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None
    except TenantAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=TENANT_ACCESS_DENIED_MESSAGE,
        ) from None

    if not _PRIVILEGED_IMPORT_ROLES.intersection(tenant_context.membership.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=TENANT_ACCESS_DENIED_MESSAGE,
        )

    return session_token, tenant_context


def _lawful_source_confirmed(request: Request) -> bool:
    value = request.headers.get(LAWFUL_SOURCE_HEADER, "").strip().lower()
    return value == "true"


@router.post(
    "/tenants/{tenant_id}/csv-imports/preview",
    response_model=CsvImportPreviewResponse,
)
async def preview_csv_import(
    tenant_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    channel_connection_id: Annotated[UUID, Query()],
    delimiter: Annotated[CsvDelimiter, Query()] = CsvDelimiter.COMMA,
    source_encoding: Annotated[CsvSourceEncoding, Query()] = CsvSourceEncoding.UTF8,
    idempotency_key: Annotated[str | None, Query()] = None,
) -> CsvImportPreviewResponse:
    _, tenant_context = await _require_privileged_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
    )

    if not _lawful_source_confirmed(request):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=VALIDATION_FAILED)

    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    if content_type != "text/csv":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=VALIDATION_FAILED
        )

    csv_bytes = await request.body()
    if len(csv_bytes) > runtime.settings.csv_max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=VALIDATION_FAILED
        )

    now = runtime.clock.now()
    try:
        preview = await runtime.csv_import_service.preview_upload(
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            creator_user_id=tenant_context.user.id,
            csv_bytes=csv_bytes,
            delimiter=delimiter,
            source_encoding=source_encoding,
            lawful_source_confirmed_at=now,
            audit_context=_audit_context(request),
            actor_type=AuditActorType.USER,
            actor_id=tenant_context.user.id,
            idempotency_key=idempotency_key,
        )
    except CsvImportValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=VALIDATION_FAILED,
        ) from error
    except CsvImportUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        ) from error
    except CsvImportServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=VALIDATION_FAILED,
        ) from error

    payload = CsvImportPreviewResponse(
        import_id=preview.import_id,
        columns=[
            CsvImportPreviewColumnResponse(index=column.index, label=column.label)
            for column in preview.columns
        ],
        total_rows=preview.total_rows,
    )
    apply_security_headers(response)
    return payload


@router.post(
    "/tenants/{tenant_id}/csv-imports/{import_id}/start",
    response_model=CsvImportStartResponse,
)
async def start_csv_import(
    tenant_id: UUID,
    import_id: UUID,
    body: CsvImportStartRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> CsvImportStartResponse:
    _, tenant_context = await _require_privileged_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
    )

    try:
        mapping = CsvColumnMapping.from_dict(body.mapping)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=VALIDATION_FAILED,
        ) from error

    try:
        started = await runtime.csv_import_service.start_import(
            tenant_id=tenant_id,
            import_id=import_id,
            mapping=mapping,
            audit_context=_audit_context(request),
            actor_type=AuditActorType.USER,
            actor_id=tenant_context.user.id,
            occurred_at=runtime.clock.now(),
        )
    except CsvImportRecordNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=VALIDATION_FAILED
        ) from error
    except CsvImportValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=VALIDATION_FAILED,
        ) from error
    except CsvImportUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        ) from error

    payload = CsvImportStartResponse(
        import_id=started.import_id, outbox_job_id=started.outbox_job_id
    )
    apply_security_headers(response)
    return payload


@router.get(
    "/tenants/{tenant_id}/csv-imports/{import_id}",
    response_model=CsvImportStatusResponse,
)
async def get_csv_import_status(
    tenant_id: UUID,
    import_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
    row_error_limit: Annotated[int, Query(ge=1, le=500)] = 100,
    row_error_offset: Annotated[int, Query(ge=0)] = 0,
) -> CsvImportStatusResponse:
    await _require_privileged_tenant_context(request, runtime, tenant_id=tenant_id)

    from closeros.application.csv_import_persistence import CsvImportRowErrorQuery

    try:
        status_view = await runtime.csv_import_service.get_status(
            tenant_id=tenant_id,
            import_id=import_id,
            row_error_query=CsvImportRowErrorQuery(
                limit=row_error_limit,
                offset=row_error_offset,
            ),
        )
    except CsvImportRecordNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=VALIDATION_FAILED
        ) from error

    payload = CsvImportStatusResponse(
        import_id=status_view.import_id,
        status=status_view.status.value,
        total_rows=status_view.total_rows,
        succeeded_count=status_view.succeeded_count,
        failed_count=status_view.failed_count,
        next_row_number=status_view.next_row_number,
        created_at=status_view.created_at,
        started_at=status_view.started_at,
        completed_at=status_view.completed_at,
        row_errors=[
            CsvImportRowErrorResponse(
                row_number=row_error.row_number,
                error_code=row_error.error_code.value,
            )
            for row_error in status_view.row_errors
        ],
    )
    apply_security_headers(response)
    return payload


@router.post(
    "/tenants/{tenant_id}/csv-imports/{import_id}/cancel",
    response_model=CsvImportAcceptedResponse,
)
async def cancel_csv_import(
    tenant_id: UUID,
    import_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> CsvImportAcceptedResponse:
    _, tenant_context = await _require_privileged_tenant_context(
        request,
        runtime,
        tenant_id=tenant_id,
    )

    try:
        await runtime.csv_import_service.cancel_import(
            tenant_id=tenant_id,
            import_id=import_id,
            audit_context=_audit_context(request),
            actor_type=AuditActorType.USER,
            actor_id=tenant_context.user.id,
            occurred_at=runtime.clock.now(),
        )
    except CsvImportRecordNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=VALIDATION_FAILED
        ) from error
    except CsvImportValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=VALIDATION_FAILED,
        ) from error
    except CsvImportUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REQUEST_UNAVAILABLE,
        ) from error

    apply_security_headers(response)
    return CsvImportAcceptedResponse()
