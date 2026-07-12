"""Browser session cookie and CSRF helpers."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new

from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import Response
from starlette.requests import Request

PRODUCTION_SESSION_COOKIE_NAME = "__Host-closeros_session"
DEVELOPMENT_SESSION_COOKIE_NAME = "closeros_dev_session"
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class SessionCookieConfig:
    name: str
    secure: bool


def session_cookie_config(*, is_production: bool) -> SessionCookieConfig:
    if is_production:
        return SessionCookieConfig(name=PRODUCTION_SESSION_COOKIE_NAME, secure=True)
    return SessionCookieConfig(name=DEVELOPMENT_SESSION_COOKIE_NAME, secure=False)


def generate_csrf_token(
    *,
    session_token: RawAuthenticationToken,
    secret: bytes,
) -> str:
    digest = hmac_new(
        secret,
        session_token.value.encode("ascii"),
        sha256,
    ).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def csrf_token_is_valid(
    *,
    session_token: RawAuthenticationToken,
    secret: bytes,
    provided_token: str,
) -> bool:
    if not isinstance(provided_token, str) or not provided_token:
        return False
    expected = generate_csrf_token(session_token=session_token, secret=secret)
    return compare_digest(expected, provided_token)


def read_session_cookie(
    request: Request,
    *,
    cookie_config: SessionCookieConfig,
) -> RawAuthenticationToken | None:
    raw_value = request.cookies.get(cookie_config.name)
    if raw_value is None:
        return None
    try:
        return RawAuthenticationToken(raw_value)
    except (TypeError, ValueError):
        return None


def set_session_cookie(
    response: Response,
    *,
    session_token: RawAuthenticationToken,
    expires_at: datetime,
    cookie_config: SessionCookieConfig,
    now: datetime,
) -> None:
    max_age = max(int((expires_at - now).total_seconds()), 0)
    response.set_cookie(
        key=cookie_config.name,
        value=session_token.value,
        max_age=max_age,
        expires=int(expires_at.timestamp()),
        path="/",
        secure=cookie_config.secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(
    response: Response,
    *,
    cookie_config: SessionCookieConfig,
) -> None:
    response.delete_cookie(
        key=cookie_config.name,
        path="/",
        secure=cookie_config.secure,
        httponly=True,
        samesite="lax",
    )


def fingerprint_value(*, secret: bytes, value: str) -> str:
    digest = hmac_new(secret, value.encode("utf-8"), sha256).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def client_ip(request: Request, *, trust_forwarded_client_ip: bool) -> str:
    if trust_forwarded_client_ip:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",", maxsplit=1)[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def origin_is_allowed(*, origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
    if origin is None:
        return False
    return origin in allowed_origins


def apply_security_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
