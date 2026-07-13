"""Tests for production SMTP notification sender with injected transport fakes."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from closeros.application.notification_ports import (
    NotificationSenderError,
    NotificationSenderTransientError,
)
from closeros.infrastructure.disabled_notification_sender import DisabledNotificationSender
from closeros.infrastructure.smtp_notification_adapter import SmtpNotificationSender


@dataclass
class FakeSmtpSession:
    host: str
    port: int
    timeout: float
    context: ssl.SSLContext
    use_implicit_tls: bool
    starttls_called: bool = False
    login_calls: list[tuple[str, str]] = field(default_factory=list)
    sent_messages: list[Any] = field(default_factory=list)
    enter_error: BaseException | None = None
    login_error: BaseException | None = None
    send_error: BaseException | None = None
    enter_delay_seconds: float = 0.0
    entered_event: threading.Event | None = None

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.starttls_called = True
        _ = context

    def login(self, user: str, password: str) -> None:
        if self.login_error is not None:
            raise self.login_error
        self.login_calls.append((user, password))

    def send_message(self, message: Any) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent_messages.append(message)

    def __enter__(self) -> FakeSmtpSession:
        if self.entered_event is not None:
            self.entered_event.set()
        if self.enter_delay_seconds:
            time.sleep(self.enter_delay_seconds)
        if self.enter_error is not None:
            raise self.enter_error
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@dataclass
class FakeSmtpFactory:
    sessions: list[FakeSmtpSession] = field(default_factory=list)
    next_session: dict[str, Any] = field(default_factory=dict)

    def __call__(
        self,
        host: str,
        port: int,
        timeout: float,
        context: ssl.SSLContext,
        use_implicit_tls: bool,
    ) -> FakeSmtpSession:
        session = FakeSmtpSession(
            host=host,
            port=port,
            timeout=timeout,
            context=context,
            use_implicit_tls=use_implicit_tls,
            **self.next_session,
        )
        self.sessions.append(session)
        return session


def _build_sender(
    *,
    factory: FakeSmtpFactory,
    use_starttls: bool = True,
    use_implicit_tls: bool = False,
    username: str = "",
    password: str = "",
) -> SmtpNotificationSender:
    return SmtpNotificationSender(
        host="smtp.example.com",
        port=587 if use_starttls else 465,
        from_address="noreply@example.com",
        use_starttls=use_starttls,
        use_implicit_tls=use_implicit_tls,
        _username=username,
        _password=password,
        _smtp_factory=factory,
    )


def test_implicit_tls_path_uses_injected_factory() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        sender = _build_sender(factory=factory, use_starttls=False, use_implicit_tls=True)
        await sender.send_email(
            recipient="user@example.com",
            subject="Hello",
            body="World",
        )
        assert len(factory.sessions) == 1
        session = factory.sessions[0]
        assert session.use_implicit_tls is True
        assert session.starttls_called is False
        assert len(session.sent_messages) == 1

    asyncio.run(exercise())


def test_starttls_path_uses_injected_factory() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        sender = _build_sender(factory=factory, use_starttls=True, use_implicit_tls=False)
        await sender.send_email(
            recipient="user@example.com",
            subject="Hello",
            body="World",
        )
        assert len(factory.sessions) == 1
        session = factory.sessions[0]
        assert session.use_implicit_tls is False
        assert session.starttls_called is True
        assert len(session.sent_messages) == 1

    asyncio.run(exercise())


def test_successful_authenticated_send() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        sender = _build_sender(
            factory=factory,
            username="smtp-user",
            password="smtp-pass",
        )
        await sender.send_email(
            recipient="user@example.com",
            subject="Hello",
            body="World",
        )
        session = factory.sessions[0]
        assert session.login_calls == [("smtp-user", "smtp-pass")]
        message = session.sent_messages[0]
        assert message["To"] == "user@example.com"
        assert message["Subject"] == "Hello"
        assert message.get_content().strip() == "World"

    asyncio.run(exercise())


def test_authentication_rejection_raises_notification_sender_error() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        factory.next_session = {
            "login_error": smtplib.SMTPAuthenticationError(535, b"auth failed"),
        }
        sender = _build_sender(factory=factory, username="smtp-user", password="smtp-pass")
        with pytest.raises(NotificationSenderError, match="smtp authentication rejected"):
            await sender.send_email(
                recipient="user@example.com",
                subject="Hello",
                body="World",
            )

    asyncio.run(exercise())


def test_transient_connect_failure_raises_transient_error() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        factory.next_session = {"enter_error": OSError("connection refused")}
        sender = _build_sender(factory=factory)
        with pytest.raises(NotificationSenderTransientError, match="smtp network failure"):
            await sender.send_email(
                recipient="user@example.com",
                subject="Hello",
                body="World",
            )

    asyncio.run(exercise())


def test_recipient_rejection_raises_notification_sender_error() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        factory.next_session = {
            "send_error": smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"no")}),
        }
        sender = _build_sender(factory=factory)
        with pytest.raises(NotificationSenderError, match="smtp recipient rejected"):
            await sender.send_email(
                recipient="user@example.com",
                subject="Hello",
                body="World",
            )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("recipient", "subject", "body", "match"),
    [
        ("user\r@example.com", "Hello", "World", "invalid characters"),
        ("user@example.com", "Hello\r", "World", "invalid characters"),
        ("user@example.com", "Hello", "", "body must not be empty"),
    ],
)
def test_send_email_rejects_invalid_input(
    recipient: str,
    subject: str,
    body: str,
    match: str,
) -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        sender = _build_sender(factory=factory)
        with pytest.raises(NotificationSenderError, match=match):
            await sender.send_email(recipient=recipient, subject=subject, body=body)

    asyncio.run(exercise())


def test_from_address_crlf_rejected_at_construct() -> None:
    with pytest.raises(NotificationSenderError, match="invalid characters"):
        SmtpNotificationSender(
            host="smtp.example.com",
            port=587,
            from_address="noreply\r@example.com",
            use_starttls=True,
            use_implicit_tls=False,
        )


def test_invalid_recipient_raises_notification_sender_error() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        sender = _build_sender(factory=factory)
        with pytest.raises(NotificationSenderError, match="email address format is invalid"):
            await sender.send_email(
                recipient="not-an-email",
                subject="Hello",
                body="World",
            )

    asyncio.run(exercise())


def test_repr_hides_secrets() -> None:
    sender = SmtpNotificationSender(
        host="smtp.example.com",
        port=587,
        from_address="noreply@example.com",
        username_reference="env:SMTP_USERNAME",
        password_reference="env:SMTP_PASSWORD",
        use_starttls=True,
        use_implicit_tls=False,
        _username="smtp-user",
        _password="smtp-pass",
    )
    rendered = repr(sender)
    assert "smtp-user" not in rendered
    assert "smtp-pass" not in rendered
    assert "env:SMTP_USERNAME" not in rendered
    assert "env:SMTP_PASSWORD" not in rendered


def test_send_email_does_not_block_event_loop() -> None:
    async def exercise() -> None:
        factory = FakeSmtpFactory()
        entered = threading.Event()
        factory.next_session = {
            "enter_delay_seconds": 0.15,
            "entered_event": entered,
        }
        sender = _build_sender(factory=factory)
        concurrent_completed = False

        async def concurrent_work() -> None:
            nonlocal concurrent_completed
            await asyncio.to_thread(entered.wait, 1.0)
            await asyncio.sleep(0.05)
            concurrent_completed = True

        send_task = asyncio.create_task(
            sender.send_email(
                recipient="user@example.com",
                subject="Hello",
                body="World",
            )
        )
        concurrent_task = asyncio.create_task(concurrent_work())
        await send_task
        await concurrent_task
        assert concurrent_completed is True

    asyncio.run(exercise())


def test_disabled_notification_sender_raises() -> None:
    async def exercise() -> None:
        sender = DisabledNotificationSender()
        with pytest.raises(NotificationSenderError, match="notification transport is disabled"):
            await sender.send_email(
                recipient="user@example.com",
                subject="Hello",
                body="World",
            )

    asyncio.run(exercise())
