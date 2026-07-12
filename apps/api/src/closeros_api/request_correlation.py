"""Server-generated request correlation identifiers."""

from __future__ import annotations

from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_CORRELATION_ID_STATE_KEY = "correlation_id"
REQUEST_CORRELATION_HEADER = "X-Request-ID"
CLIENT_REQUEST_ID_HEADER = "X-Request-ID"


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Assign a fresh server-side correlation ID to every HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = uuid4()
        setattr(request.state, REQUEST_CORRELATION_ID_STATE_KEY, correlation_id)
        response = await call_next(request)
        response.headers[REQUEST_CORRELATION_HEADER] = str(correlation_id)
        return response


def get_request_correlation_id(request: Request) -> UUID:
    correlation_id = getattr(request.state, REQUEST_CORRELATION_ID_STATE_KEY, None)
    if isinstance(correlation_id, UUID):
        return correlation_id
    raise RuntimeError("request correlation ID is not configured")
