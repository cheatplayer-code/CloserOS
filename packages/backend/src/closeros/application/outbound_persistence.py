"""Application persistence ports for outbound messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.persistence_errors import PersistenceError
from closeros.domain.outbound_message import OutboundMessageKind, OutboundMessageStatus


class OutboundPersistenceError(PersistenceError):
    """Base class for outbound message persistence failures."""


class OutboundMessageNotFoundError(OutboundPersistenceError):
    """Raised when an outbound message cannot be found."""


class OutboundMessageVersionConflictError(OutboundPersistenceError):
    """Raised when optimistic concurrency detects a stale version."""


@dataclass(frozen=True, slots=True)
class OutboundMessageRecord:
    id: UUID
    tenant_id: UUID
    conversation_thread_id: UUID
    channel_connection_id: UUID
    kind: OutboundMessageKind
    status: OutboundMessageStatus
    encrypted_content_id: UUID
    provider_template_id: UUID | None
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    provider_message_id: str | None
    failure_code: str | None
    created_at: datetime
    approved_at: datetime | None
    queued_at: datetime | None
    sent_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class OutboundDeliveryAttemptRecord:
    id: UUID
    tenant_id: UUID
    outbound_message_id: UUID
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    outcome: str
    error_code: str | None


class OutboundMessageRepository(Protocol):
    async def add(self, *, record: OutboundMessageRecord) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> OutboundMessageRecord | None: ...

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> OutboundMessageRecord | None: ...

    async def get_by_provider_message_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        provider_message_id: str,
    ) -> OutboundMessageRecord | None: ...

    async def update(
        self,
        *,
        record: OutboundMessageRecord,
        expected_version: int,
    ) -> OutboundMessageRecord: ...

    async def list_delivery_unknown(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> tuple[OutboundMessageRecord, ...]: ...

    async def list_stale_sending(
        self,
        *,
        tenant_id: UUID,
        stale_before: datetime,
        limit: int,
    ) -> tuple[OutboundMessageRecord, ...]: ...


class OutboundDeliveryAttemptRepository(Protocol):
    async def add(self, *, record: OutboundDeliveryAttemptRecord) -> None: ...

    async def list_for_message(
        self,
        *,
        tenant_id: UUID,
        outbound_message_id: UUID,
    ) -> tuple[OutboundDeliveryAttemptRecord, ...]: ...
