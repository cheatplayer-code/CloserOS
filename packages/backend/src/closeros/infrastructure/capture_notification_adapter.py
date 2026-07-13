"""Capture notification sender for development and tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CapturedEmail:
    recipient: str
    subject: str
    body: str


@dataclass
class CaptureNotificationSender:
    sent: list[CapturedEmail] = field(default_factory=list)
    fail_next: Exception | None = None

    async def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
    ) -> None:
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise error
        self.sent.append(
            CapturedEmail(
                recipient=recipient,
                subject=subject,
                body=body,
            )
        )


__all__ = ["CaptureNotificationSender", "CapturedEmail"]
