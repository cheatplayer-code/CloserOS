"""Provider webhook ingestion HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from closeros.application.audit_recording import AuditContext
from closeros.application.webhook_ingestion import (
    WEBHOOK_DENIED_RESPONSE,
    WebhookIngestionDeniedError,
)
from closeros.domain.canonical_enums import ProviderKind
from fastapi import APIRouter, Depends, Request, Response, status
from starlette.exceptions import HTTPException

from closeros_api.auth_security import apply_security_headers
from closeros_api.composition import ApiRuntime
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["webhooks"])

WEBHOOK_ACCEPTED = "accepted"


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


def _provider_kind_from_path(value: str) -> ProviderKind | None:
    try:
        return ProviderKind(value.strip().lower())
    except ValueError:
        return None


def _deny() -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=WEBHOOK_DENIED_RESPONSE)


@router.post("/webhooks/{provider}/{connection_id}")
async def accept_provider_webhook(
    provider: str,
    connection_id: UUID,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> dict[str, str]:
    provider_kind = _provider_kind_from_path(provider)
    if provider_kind is None:
        _deny()

    content_length_header = request.headers.get("content-length")
    content_length = int(content_length_header) if content_length_header else None
    if content_length is not None and content_length > runtime.settings.webhook_max_body_bytes:
        _deny()

    raw_body = await request.body()
    if len(raw_body) > runtime.settings.webhook_max_body_bytes:
        _deny()

    normalized_headers = {key: value for key, value in request.headers.items()}

    try:
        result = await runtime.webhook_ingestion.accept_provider_webhook(
            provider_kind=provider_kind,  # type: ignore[arg-type]
            connection_id=connection_id,
            raw_body=raw_body,
            headers=normalized_headers,
            content_length=content_length,
            audit_context=_audit_context(request),
            received_at=runtime.clock.now(),
        )
    except WebhookIngestionDeniedError:
        _deny()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal error",
        ) from error

    if not result.accepted:
        _deny()

    apply_security_headers(response)
    return {"status": WEBHOOK_ACCEPTED}
