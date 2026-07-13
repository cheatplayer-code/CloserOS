"""Encrypted notification payload schema (persisted only inside encrypted content)."""

from __future__ import annotations

import json
from dataclasses import dataclass

_NOTIFICATION_PAYLOAD_VERSION = 1
_SUBJECT_MAX_LENGTH = 998
_BODY_MAX_LENGTH = 64 * 1024


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    """Recipient, subject, body and optional one-time URL stored encrypted only."""

    recipient: str
    subject: str
    body: str

    def __post_init__(self) -> None:
        if not isinstance(self.recipient, str) or "@" not in self.recipient:
            raise ValueError("recipient must be a valid email address")
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("subject must not be empty")
        if len(self.subject.strip()) > _SUBJECT_MAX_LENGTH:
            raise ValueError("subject exceeds maximum length")
        if not isinstance(self.body, str) or not self.body:
            raise ValueError("body must not be empty")
        if len(self.body) > _BODY_MAX_LENGTH:
            raise ValueError("body exceeds maximum length")

    def to_json_bytes(self) -> bytes:
        document = {
            "version": _NOTIFICATION_PAYLOAD_VERSION,
            "recipient": self.recipient.strip(),
            "subject": self.subject.strip(),
            "body": self.body,
        }
        return json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> NotificationPayload:
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("payload must be non-empty bytes")
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("payload document must be an object")
        version = document.get("version")
        if version != _NOTIFICATION_PAYLOAD_VERSION:
            raise ValueError("unsupported notification payload version")
        recipient = document.get("recipient")
        subject = document.get("subject")
        body = document.get("body")
        if (
            not isinstance(recipient, str)
            or not isinstance(subject, str)
            or not isinstance(body, str)
        ):
            raise ValueError("notification payload fields are invalid")
        return cls(recipient=recipient, subject=subject, body=body)

    def __repr__(self) -> str:
        return "NotificationPayload(recipient=<redacted>, subject=<redacted>, body=<redacted>)"


# Platform tenant used for auth-scoped notifications without a business tenant.
PLATFORM_NOTIFICATION_TENANT_ID_STR = "00000000-0000-0000-0000-0000000000f0"


__all__ = [
    "NotificationPayload",
    "PLATFORM_NOTIFICATION_TENANT_ID_STR",
]
