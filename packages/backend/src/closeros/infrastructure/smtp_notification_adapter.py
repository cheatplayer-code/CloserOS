"""Production SMTP notification sender with async-safe transport."""

from __future__ import annotations

import asyncio
import re
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Any

from closeros.application.notification_ports import (
    NotificationSenderError,
    NotificationSenderTransientError,
)

_CRLF_PATTERN = re.compile(r"[\r\n]")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _reject_header_injection(value: str, *, field_name: str) -> str:
    if _CRLF_PATTERN.search(value):
        raise NotificationSenderError(f"{field_name} contains invalid characters")
    normalized = value.strip()
    if not normalized:
        raise NotificationSenderError(f"{field_name} must not be empty")
    return normalized


def _validate_email_address(value: str) -> str:
    normalized = _reject_header_injection(value, field_name="email")
    _, parsed = parseaddr(normalized)
    candidate = parsed or normalized
    if not _EMAIL_PATTERN.fullmatch(candidate):
        raise NotificationSenderError("email address format is invalid")
    return candidate


@dataclass(frozen=True, slots=True)
class SmtpNotificationSender:
    host: str
    port: int
    from_address: str
    use_starttls: bool = True
    use_implicit_tls: bool = False
    timeout_seconds: float = 30.0
    username_reference: str | None = None
    password_reference: str | None = None
    _username: str = field(default="", repr=False, compare=False)
    _password: str = field(default="", repr=False, compare=False)
    _smtp_factory: Callable[..., Any] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.use_starttls and self.use_implicit_tls:
            raise ValueError("cannot enable both STARTTLS and implicit TLS")
        if not self.use_starttls and not self.use_implicit_tls:
            raise ValueError("SMTP transport must use TLS")
        _validate_email_address(self.from_address)

    def __repr__(self) -> str:
        return f"SmtpNotificationSender(host={self.host!r}, port={self.port})"

    async def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
    ) -> None:
        validated_recipient = _validate_email_address(recipient)
        validated_subject = _reject_header_injection(subject, field_name="subject")
        validated_body = body if body else ""
        if not validated_body:
            raise NotificationSenderError("body must not be empty")

        try:
            await asyncio.to_thread(
                self._send_sync,
                validated_recipient,
                validated_subject,
                validated_body,
            )
        except NotificationSenderError:
            raise
        except smtplib.SMTPAuthenticationError as exc:
            raise NotificationSenderError("smtp authentication rejected") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise NotificationSenderError("smtp recipient rejected") from exc
        except (TimeoutError, smtplib.SMTPServerDisconnected, OSError) as exc:
            raise NotificationSenderTransientError("smtp network failure") from exc
        except smtplib.SMTPException as exc:
            raise NotificationSenderTransientError("smtp delivery failed") from exc

    def _send_sync(self, recipient: str, subject: str, body: str) -> None:
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body.replace("\r\n", "\n").replace("\r", "\n"))

        context = ssl.create_default_context()
        if self._smtp_factory is not None:
            with self._smtp_factory(
                self.host,
                self.port,
                self.timeout_seconds,
                context,
                self.use_implicit_tls,
            ) as smtp:
                if not self.use_implicit_tls:
                    smtp.starttls(context=context)
                self._login_if_needed(smtp)
                smtp.send_message(message)
            return

        if self.use_implicit_tls:
            with smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
                context=context,
            ) as smtp:
                self._login_if_needed(smtp)
                smtp.send_message(message)
            return

        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
            smtp.starttls(context=context)
            self._login_if_needed(smtp)
            smtp.send_message(message)

    def _login_if_needed(self, smtp: smtplib.SMTP) -> None:
        if self._username:
            smtp.login(self._username, self._password)


__all__ = ["SmtpNotificationSender"]
