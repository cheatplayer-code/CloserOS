"""Typed API settings loaded from the environment at call time."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlparse
from uuid import UUID

_MIN_SECRET_LENGTH = 32
_DEVELOPMENT = "development"
_STAGING = "staging"
_PRODUCTION = "production"
_MANAGED_ENVIRONMENTS = frozenset({_STAGING, _PRODUCTION})
_DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/"


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
    webhook_max_body_bytes: int
    csv_max_body_bytes: int
    ingestion_service_id: UUID
    ai_external_calls_enabled: bool = False
    deepseek_api_key: str | None = field(default=None, repr=False)
    deepseek_base_url: str = _DEFAULT_DEEPSEEK_BASE_URL
    deepseek_model: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == _PRODUCTION

    @property
    def is_staging(self) -> bool:
        return self.app_env == _STAGING

    @property
    def is_development(self) -> bool:
        return self.app_env == _DEVELOPMENT

    @property
    def is_managed(self) -> bool:
        return self.app_env in _MANAGED_ENVIRONMENTS

    @classmethod
    def from_env(cls) -> ApiSettings:
        app_env = os.environ.get("APP_ENV", _DEVELOPMENT).strip().lower()
        if app_env not in {_DEVELOPMENT, _STAGING, _PRODUCTION}:
            raise ApiConfigurationError("APP_ENV must be development, staging, or production")

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

        webhook_max_body_bytes = _positive_int_from_env(
            variable_name="WEBHOOK_MAX_BODY_BYTES",
            default=1_048_576,
        )
        csv_max_body_bytes = _positive_int_from_env(
            variable_name="CSV_MAX_BODY_BYTES",
            default=10_485_760,
        )
        ingestion_service_id = _ingestion_service_id_from_env(app_env=app_env)
        ai_external_calls_enabled = _boolean_from_env(
            variable_name="AI_EXTERNAL_CALLS_ENABLED",
            default=False,
        )
        deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or None
        deepseek_base_url = _https_base_url_from_env(
            variable_name="DEEPSEEK_BASE_URL",
            default=_DEFAULT_DEEPSEEK_BASE_URL,
        )
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "").strip() or None

        return cls(
            app_env=app_env,
            database_url=database_url,
            auth_allowed_origins=origins,
            auth_csrf_secret=csrf_secret,
            auth_rate_limit_secret=rate_limit_secret,
            session_touch_interval=timedelta(minutes=touch_value),
            trust_forwarded_client_ip=trust_forwarded == "true",
            webhook_max_body_bytes=webhook_max_body_bytes,
            csv_max_body_bytes=csv_max_body_bytes,
            ingestion_service_id=ingestion_service_id,
            ai_external_calls_enabled=ai_external_calls_enabled,
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model,
        )

    def validate_for_runtime(self) -> None:
        _validate_external_ai_settings(self)
        if self.is_development:
            for origin in self.auth_allowed_origins:
                parsed = urlparse(origin)
                if parsed.scheme not in {"http", "https"}:
                    raise ApiConfigurationError("allowed origins must use http or https")
            return

        if len(self.auth_csrf_secret) < _MIN_SECRET_LENGTH:
            raise ApiConfigurationError("AUTH_CSRF_SECRET is too weak for a managed environment")
        if len(self.auth_rate_limit_secret) < _MIN_SECRET_LENGTH:
            raise ApiConfigurationError(
                "AUTH_RATE_LIMIT_SECRET is too weak for a managed environment"
            )

        for origin in self.auth_allowed_origins:
            parsed = urlparse(origin)
            if parsed.scheme != "https":
                raise ApiConfigurationError("managed allowed origins must use https")
            if not parsed.netloc:
                raise ApiConfigurationError("managed allowed origins must include a host")


def _boolean_from_env(*, variable_name: str, default: bool) -> bool:
    raw_value = os.environ.get(variable_name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ApiConfigurationError(
        f"{variable_name} must be one of true/false, 1/0, yes/no, or on/off"
    )


def _https_base_url_from_env(*, variable_name: str, default: str) -> str:
    raw_value = os.environ.get(variable_name, "").strip() or default
    parsed = urlparse(raw_value)
    if parsed.scheme != "https":
        raise ApiConfigurationError(f"{variable_name} must use https")
    if not parsed.netloc:
        raise ApiConfigurationError(f"{variable_name} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ApiConfigurationError(f"{variable_name} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ApiConfigurationError(f"{variable_name} must not contain query or fragment")
    return raw_value if raw_value.endswith("/") else f"{raw_value}/"


def _validate_external_ai_settings(settings: ApiSettings) -> None:
    if not settings.ai_external_calls_enabled:
        return
    if settings.deepseek_api_key is None:
        raise ApiConfigurationError("AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_API_KEY")
    if settings.deepseek_model is None:
        raise ApiConfigurationError("AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_MODEL")
    parsed = urlparse(settings.deepseek_base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ApiConfigurationError(
            "AI_EXTERNAL_CALLS_ENABLED requires a valid HTTPS DEEPSEEK_BASE_URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ApiConfigurationError("DEEPSEEK_BASE_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ApiConfigurationError("DEEPSEEK_BASE_URL must not contain query or fragment")


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
    if app_env in _MANAGED_ENVIRONMENTS and len(encoded) < _MIN_SECRET_LENGTH:
        raise ApiConfigurationError(f"{variable_name} is too weak for a managed environment")
    return encoded


def _positive_int_from_env(*, variable_name: str, default: int) -> int:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as error:
        raise ApiConfigurationError(f"{variable_name} must be an integer") from error
    if parsed <= 0:
        raise ApiConfigurationError(f"{variable_name} must be positive")
    return parsed


def _ingestion_service_id_from_env(*, app_env: str) -> UUID:
    raw_value = os.environ.get("INGESTION_SERVICE_ID", "").strip()
    if raw_value:
        try:
            return UUID(raw_value)
        except ValueError as error:
            raise ApiConfigurationError("INGESTION_SERVICE_ID must be a UUID") from error
    if app_env == _DEVELOPMENT:
        return uuid.uuid4()
    raise ApiConfigurationError("INGESTION_SERVICE_ID is not set")
