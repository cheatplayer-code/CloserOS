"""Factory for notification sender adapters."""

from __future__ import annotations

import os

from closeros.application.notification_ports import NotificationSender
from closeros.application.secret_ports import SecretResolver
from closeros.infrastructure.capture_notification_adapter import CaptureNotificationSender
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver
from closeros.infrastructure.smtp_notification_adapter import SmtpNotificationSender


class NotificationTransportConfigurationError(RuntimeError):
    """Raised when notification transport configuration is invalid."""


def build_notification_sender_sync(
    *,
    app_env: str,
    secret_resolver: SecretResolver | None = None,
) -> NotificationSender:
    enabled = os.environ.get("NOTIFICATIONS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    is_production = app_env.strip().lower() in {"production", "staging"}
    resolver = secret_resolver or EnvSecretResolver()

    if not enabled:
        if is_production:
            from closeros.infrastructure.disabled_notification_sender import (
                DisabledNotificationSender,
            )

            return DisabledNotificationSender()
        return CaptureNotificationSender()

    if not is_production:
        return CaptureNotificationSender()

    host = os.environ.get("SMTP_HOST", "").strip()
    port_raw = os.environ.get("SMTP_PORT", "").strip()
    from_address = os.environ.get("SMTP_FROM_ADDRESS", "").strip()
    username_ref = os.environ.get("SMTP_USERNAME_REF", "").strip() or None
    password_ref = os.environ.get("SMTP_PASSWORD_REF", "").strip() or None
    transport = os.environ.get("SMTP_TRANSPORT", "starttls").strip().lower()

    if not host or not port_raw or not from_address:
        raise NotificationTransportConfigurationError(
            "production notifications require SMTP_HOST, SMTP_PORT, and SMTP_FROM_ADDRESS"
        )

    port = int(port_raw)
    username = ""
    password = ""
    if username_ref and hasattr(resolver, "resolve_secret_sync"):
        username = resolver.resolve_secret_sync(reference=username_ref).decode("utf-8")
    if password_ref and hasattr(resolver, "resolve_secret_sync"):
        password = resolver.resolve_secret_sync(reference=password_ref).decode("utf-8")

    use_starttls = transport == "starttls"
    use_implicit_tls = transport == "tls"
    if transport not in {"starttls", "tls"}:
        raise NotificationTransportConfigurationError("SMTP_TRANSPORT must be starttls or tls")

    return SmtpNotificationSender(
        host=host,
        port=port,
        from_address=from_address,
        use_starttls=use_starttls,
        use_implicit_tls=use_implicit_tls,
        username_reference=username_ref,
        password_reference=password_ref,
        _username=username,
        _password=password,
    )


def require_notification_transport_configured(*, app_env: str) -> None:
    is_production = app_env.strip().lower() in {"production", "staging"}
    enabled = os.environ.get("NOTIFICATIONS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if is_production and enabled:
        missing = [
            name
            for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM_ADDRESS")
            if not os.environ.get(name, "").strip()
        ]
        if missing:
            raise NotificationTransportConfigurationError(
                "production notifications enabled but SMTP configuration is incomplete"
            )


__all__ = [
    "NotificationTransportConfigurationError",
    "build_notification_sender_sync",
    "require_notification_transport_configured",
]
