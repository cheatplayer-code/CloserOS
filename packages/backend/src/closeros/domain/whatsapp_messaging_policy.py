"""Versioned WhatsApp messaging policy based on official Meta rules.

Documentation review date: 2026-07-12
Graph API version: v21.0

Policy v1 encodes the customer service window: free-form replies are permitted
only within 24 hours of the customer's last inbound message. Outside that
window, only approved template messages may be sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from closeros.domain.outbound_message import OutboundMessageKind

WHATSAPP_MESSAGING_POLICY_VERSION = "whatsapp_messaging_policy_v1"
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)
DOCUMENTATION_REVIEW_DATE = "2026-07-12"
GRAPH_API_VERSION = "v21.0"


class MessagingPolicyViolation(StrEnum):
    TEMPLATE_REQUIRED = "template_required"
    FREE_FORM_NOT_ALLOWED = "free_form_not_allowed"
    TEMPLATE_NOT_ALLOWED = "template_not_allowed"
    WINDOW_UNKNOWN = "window_unknown"


class WhatsAppMessagingPolicyError(ValueError):
    """Raised when outbound messaging violates the versioned policy."""


@dataclass(frozen=True, slots=True)
class MessagingPolicyDecision:
    allowed: bool
    violation: MessagingPolicyViolation | None = None

    def __post_init__(self) -> None:
        if self.allowed and self.violation is not None:
            raise ValueError("allowed decisions must not include a violation")
        if not self.allowed and self.violation is None:
            raise ValueError("denied decisions require a violation")


@dataclass(frozen=True, slots=True)
class WhatsAppMessagingPolicy:
    """Versioned policy evaluator for outbound WhatsApp messages."""

    version: str = WHATSAPP_MESSAGING_POLICY_VERSION
    customer_service_window: timedelta = CUSTOMER_SERVICE_WINDOW

    def __post_init__(self) -> None:
        if self.version != WHATSAPP_MESSAGING_POLICY_VERSION:
            raise ValueError("unsupported messaging policy version")
        if self.customer_service_window <= timedelta(0):
            raise ValueError("customer_service_window must be positive")

    def evaluate_send(
        self,
        *,
        kind: OutboundMessageKind,
        last_customer_inbound_at: datetime | None,
        now: datetime,
    ) -> MessagingPolicyDecision:
        if not isinstance(kind, OutboundMessageKind):
            raise TypeError("kind must be an OutboundMessageKind")

        if kind is OutboundMessageKind.APPROVED_TEMPLATE:
            return MessagingPolicyDecision(allowed=True)

        if last_customer_inbound_at is None:
            return MessagingPolicyDecision(
                allowed=False,
                violation=MessagingPolicyViolation.TEMPLATE_REQUIRED,
            )

        if last_customer_inbound_at.tzinfo is None or last_customer_inbound_at.utcoffset() is None:
            raise WhatsAppMessagingPolicyError("last_customer_inbound_at must be timezone-aware")

        window_end = last_customer_inbound_at + self.customer_service_window
        if now <= window_end:
            return MessagingPolicyDecision(allowed=True)

        return MessagingPolicyDecision(
            allowed=False,
            violation=MessagingPolicyViolation.TEMPLATE_REQUIRED,
        )

    def require_allowed(
        self,
        *,
        kind: OutboundMessageKind,
        last_customer_inbound_at: datetime | None,
        now: datetime,
    ) -> None:
        decision = self.evaluate_send(
            kind=kind,
            last_customer_inbound_at=last_customer_inbound_at,
            now=now,
        )
        if not decision.allowed:
            violation = decision.violation.value if decision.violation else "denied"
            raise WhatsAppMessagingPolicyError(f"messaging policy violation: {violation}")


__all__ = [
    "CUSTOMER_SERVICE_WINDOW",
    "DOCUMENTATION_REVIEW_DATE",
    "GRAPH_API_VERSION",
    "MessagingPolicyDecision",
    "MessagingPolicyViolation",
    "WHATSAPP_MESSAGING_POLICY_VERSION",
    "WhatsAppMessagingPolicy",
    "WhatsAppMessagingPolicyError",
]
