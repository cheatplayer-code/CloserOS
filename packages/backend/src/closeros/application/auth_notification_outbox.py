"""Bridges authentication notification deliveries to the transactional outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.authentication_notification_delivery import (
    AuthenticationNotificationDelivery,
)
from closeros.application.notification_delivery_service import NotificationDeliveryService
from closeros.domain.authentication import AuthenticationTokenPurpose


class AuthenticationNotificationPublisher(Protocol):
    async def publish(
        self,
        *,
        delivery: AuthenticationNotificationDelivery,
        purpose: AuthenticationTokenPurpose,
        tenant_id: UUID | None,
        requested_at: datetime,
    ) -> UUID | None: ...


@dataclass(frozen=True, slots=True)
class OutboxAuthenticationNotificationPublisher:
    """Enqueues authentication notifications for asynchronous delivery."""

    delivery_service: NotificationDeliveryService

    async def publish(
        self,
        *,
        delivery: AuthenticationNotificationDelivery,
        purpose: AuthenticationTokenPurpose,
        tenant_id: UUID | None,
        requested_at: datetime,
    ) -> UUID | None:
        return await self.delivery_service.enqueue_authentication_notification(
            delivery=delivery,
            purpose=purpose,
            tenant_id=tenant_id,
            requested_at=requested_at,
        )


@dataclass(frozen=True, slots=True)
class PassthroughAuthenticationNotificationPublisher:
    """Returns delivery to the caller for synchronous dispatch (development default)."""

    async def publish(
        self,
        *,
        delivery: AuthenticationNotificationDelivery,
        purpose: AuthenticationTokenPurpose,
        tenant_id: UUID | None,
        requested_at: datetime,
    ) -> UUID | None:
        return None


__all__ = [
    "AuthenticationNotificationPublisher",
    "OutboxAuthenticationNotificationPublisher",
    "PassthroughAuthenticationNotificationPublisher",
]
