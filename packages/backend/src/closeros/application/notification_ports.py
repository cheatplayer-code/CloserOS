"""Application ports for notification delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.notification import (
    NotificationAttemptOutcome,
    NotificationDelivery,
    NotificationDeliveryStatus,
)


class NotificationPersistenceError(PersistenceError):
    """Base class for notification persistence failures."""


class NotificationDeliveryNotFoundError(NotificationPersistenceError):
    """Raised when a notification delivery does not exist."""


@dataclass(frozen=True, slots=True)
class NotificationDeliveryAttemptRecord:
    id: UUID
    tenant_id: UUID | None
    delivery_id: UUID
    attempt_number: int
    outcome: NotificationAttemptOutcome
    error_code: str | None
    started_at: datetime
    finished_at: datetime


class NotificationDeliveryRepository(Protocol):
    async def add(self, *, delivery: NotificationDelivery) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID | None,
        delivery_id: UUID,
    ) -> NotificationDelivery | None: ...

    async def update_status(
        self,
        *,
        tenant_id: UUID | None,
        delivery_id: UUID,
        status: NotificationDeliveryStatus,
        updated_at: datetime,
        delivered_at: datetime | None = None,
        last_error_code: str | None = None,
        attempt_count: int | None = None,
        clear_encrypted_payload_content_id: bool = False,
    ) -> None: ...


class NotificationDeliveryAttemptRepository(Protocol):
    async def add(self, *, attempt: NotificationDeliveryAttemptRecord) -> None: ...


class NotificationSender(Protocol):
    """Port for delivering rendered notification content."""

    async def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
    ) -> None: ...


class NotificationSenderError(Exception):
    """Permanent notification transport failure."""


class NotificationSenderTransientError(NotificationSenderError):
    """Transient notification transport failure suitable for retry."""


__all__ = [
    "NotificationDeliveryAttemptRecord",
    "NotificationDeliveryAttemptRepository",
    "NotificationDeliveryNotFoundError",
    "NotificationDeliveryRepository",
    "NotificationPersistenceError",
    "NotificationSender",
    "NotificationSenderError",
    "NotificationSenderTransientError",
]
