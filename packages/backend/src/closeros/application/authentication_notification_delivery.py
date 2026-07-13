"""Authentication notification delivery payload shared across workflow and outbox."""

from __future__ import annotations

from dataclasses import dataclass, field

from closeros.domain.authentication import AuthenticationEmail
from closeros.security.authentication_tokens import RawAuthenticationToken


@dataclass(frozen=True, slots=True)
class AuthenticationNotificationDelivery:
    """Internal email-delivery payload hidden from public repr."""

    recipient: AuthenticationEmail = field(repr=False)
    raw_token: RawAuthenticationToken = field(repr=False)


__all__ = ["AuthenticationNotificationDelivery"]
