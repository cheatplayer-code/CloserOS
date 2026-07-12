"""Typed API settings loaded from the environment at call time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

_MIN_SECRET_LENGTH = 32
_DEVELOPMENT = "development"
_PRODUCTION = "production"


class ApiConfigurationError(RuntimeError):
    """Raised when API settings are missing or unsafe for the active environment."""


@dataclass(frozen=True, slots=True)
class ApiSettings:
    app_env: str
    database_url: str
    auth_allowed_origins: tuple[str, ...]
    auth_csrf_secret: bytes
    auth_rate_limit_secret: bytes
    session_touch_interval: timedelta
    trust_forwarded_client_ip: bool

    @property
    def is_production(self) -> bool:
        return self.app_env == _PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == _DEVELOPMENT

    @classmethod
    def from_env(cls) -> ApiSettings:
        app_env = os.environ.get("APP_ENV", _DEVELOPMENT).strip().lower()
        if app_env not in {_DEVELOPMENT, _PRODUCTION}:
            raise ApiConfigurationError("APP_ENV must be development or production")

        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ApiConfigurationError("DATABASE_URL is not set")

        origins_raw = os.environ.get("AUTH_ALLOWED_ORIGINS", "").strip()
        if not origins_raw:
            if app_env == _DEVELOPMENT:
                origins_raw = "http://127.0.0.1:3000,http://localhost:3000"
            else:
                raise ApiConfigurationError("AUTH_ALLOWED_ORIGINS is not set")

        origins = tuple(origin.strip() for origin in origins_raw.split(",") if origin.strip())
        if not origins:
            raise ApiConfigurationError("AUTH_ALLOWED_ORIGINS must not be empty")

        csrf_secret = _secret_from_env(
            variable_name="AUTH_CSRF_SECRET",
            app_env=app_env,
            development_fallback=b"closeros_local_csrf_only_not_production_32b",
        )
        rate_limit_secret = _secret_from_env(
            variable_name="AUTH_RATE_LIMIT_SECRET",
            app_env=app_env,
            development_fallback=b"closeros_local_rate_only_not_production_32b",
        )

        touch_minutes = os.environ.get("AUTH_SESSION_TOUCH_MINUTES", "5").strip()
        try:
            touch_value = int(touch_minutes)
        except ValueError as error:
            raise ApiConfigurationError("AUTH_SESSION_TOUCH_MINUTES must be an integer") from error
        if touch_value <= 0:
            raise ApiConfigurationError("AUTH_SESSION_TOUCH_MINUTES must be positive")

        trust_forwarded = os.environ.get("AUTH_TRUST_FORWARDED_CLIENT_IP", "false").strip().lower()
        if trust_forwarded not in {"true", "false"}:
            raise ApiConfigurationError("AUTH_TRUST_FORWARDED_CLIENT_IP must be true or false")

        return cls(
            app_env=app_env,
            database_url=database_url,
            auth_allowed_origins=origins,
            auth_csrf_secret=csrf_secret,
            auth_rate_limit_secret=rate_limit_secret,
            session_touch_interval=timedelta(minutes=touch_value),
            trust_forwarded_client_ip=trust_forwarded == "true",
        )

    def validate_for_runtime(self) -> None:
        if self.is_development:
            for origin in self.auth_allowed_origins:
                parsed = urlparse(origin)
                if parsed.scheme not in {"http", "https"}:
                    raise ApiConfigurationError("allowed origins must use http or https")
            return

        if len(self.auth_csrf_secret) < _MIN_SECRET_LENGTH:
            raise ApiConfigurationError("AUTH_CSRF_SECRET is too weak for production")
        if len(self.auth_rate_limit_secret) < _MIN_SECRET_LENGTH:
            raise ApiConfigurationError("AUTH_RATE_LIMIT_SECRET is too weak for production")

        for origin in self.auth_allowed_origins:
            parsed = urlparse(origin)
            if parsed.scheme != "https":
                raise ApiConfigurationError("production allowed origins must use https")
            if not parsed.netloc:
                raise ApiConfigurationError("production allowed origins must include a host")


def _secret_from_env(
    *,
    variable_name: str,
    app_env: str,
    development_fallback: bytes,
) -> bytes:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        if app_env == _DEVELOPMENT:
            return development_fallback
        raise ApiConfigurationError(f"{variable_name} is not set")

    encoded = raw_value.encode("utf-8")
    if app_env == _PRODUCTION and len(encoded) < _MIN_SECRET_LENGTH:
        raise ApiConfigurationError(f"{variable_name} is too weak for production")
    return encoded
