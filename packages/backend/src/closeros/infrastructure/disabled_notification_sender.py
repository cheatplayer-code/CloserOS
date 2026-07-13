"""Notification sender that fails closed when notifications are disabled in production."""

from __future__ import annotations

from closeros.application.notification_ports import NotificationSenderError


class DisabledNotificationSender:
    """Raises on delivery attempts; production must not silently discard notifications."""

    async def send_email(self, *, recipient: str, subject: str, body: str) -> None:
        _ = recipient, subject, body
        raise NotificationSenderError("notification transport is disabled")


__all__ = ["DisabledNotificationSender"]
