"""Application-layer persistence ports for canonical conversation entities.

These protocols define repository and unit-of-work contracts for channel
connections, conversation threads, messages, and related immutable events.
The application layer must never import SQLAlchemy or other persistence
technology; concrete implementations live in the infrastructure layer.

All tenant-owned lookups require an explicit ``tenant_id``. Repositories flush
but never commit; the unit of work owns commit and rollback.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from closeros.application.audit_persistence import AuditEventAppendRepository
from closeros.application.persistence_errors import PersistenceError
from closeros.domain.canonical_enums import ProviderKind, WebhookProcessingStatus
from closeros.domain.channel_connection import ChannelConnection
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.crm_outcome import CRMOutcome
from closeros.domain.lead import Lead
from closeros.domain.manager_assignment import ManagerAssignment
from closeros.domain.message import Message
from closeros.domain.message_events import (
    MessageDeletionEvent,
    MessageDeliveryStatusEvent,
    MessageEditEvent,
)
from closeros.domain.sales_case import SalesCase
from closeros.domain.webhook_event import WebhookEvent


class CanonicalPersistenceError(PersistenceError):
    """Base class for safe canonical persistence failures.

    Instances must never carry message bodies, provider payloads, tokens,
    secrets, or SQL fragments in their messages.
    """


class CanonicalRecordNotFoundError(CanonicalPersistenceError):
    """Raised when an update targets a record that does not exist."""


class CanonicalReferenceError(CanonicalPersistenceError):
    """Raised when a referenced tenant-owned record does not exist."""


class DuplicateChannelConnectionError(CanonicalPersistenceError):
    """Raised when a channel connection external identifier already exists."""


class DuplicateLeadError(CanonicalPersistenceError):
    """Raised when a lead external identity already exists."""


class DuplicateConversationThreadError(CanonicalPersistenceError):
    """Raised when a conversation thread external identifier already exists."""


class DuplicateMessageError(CanonicalPersistenceError):
    """Raised when a message external identifier already exists."""


class DuplicateMessageEditEventError(CanonicalPersistenceError):
    """Raised when a message edit event external identifier already exists."""


class DuplicateMessageDeletionEventError(CanonicalPersistenceError):
    """Raised when a message deletion event external identifier already exists."""


class DuplicateMessageDeliveryStatusEventError(CanonicalPersistenceError):
    """Raised when a delivery status event external identifier already exists."""


class DuplicateCRMOutcomeError(CanonicalPersistenceError):
    """Raised when a CRM outcome external deal identifier already exists."""


class DuplicateWebhookEventError(CanonicalPersistenceError):
    """Raised when a webhook event external identifier already exists."""


class ChannelConnectionRepository(Protocol):
    async def add(self, connection: ChannelConnection) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> ChannelConnection | None: ...

    async def get_by_connection_id(self, *, connection_id: UUID) -> ChannelConnection | None: ...

    async def get_by_provider_external_id(
        self,
        *,
        tenant_id: UUID,
        provider: ProviderKind,
        external_connection_id: str,
    ) -> ChannelConnection | None: ...

    async def update(self, connection: ChannelConnection) -> None: ...


class LeadRepository(Protocol):
    async def add(self, lead: Lead) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        lead_id: UUID,
    ) -> Lead | None: ...

    async def get_by_external_identity_id(
        self,
        *,
        tenant_id: UUID,
        external_identity_id: str,
    ) -> Lead | None: ...

    async def update(self, lead: Lead) -> None: ...


class SalesCaseRepository(Protocol):
    async def add(self, sales_case: SalesCase) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        sales_case_id: UUID,
    ) -> SalesCase | None: ...

    async def update(self, sales_case: SalesCase) -> None: ...


class ConversationThreadRepository(Protocol):
    async def add(self, thread: ConversationThread) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> ConversationThread | None: ...

    async def get_by_external_conversation_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        external_conversation_id: str,
    ) -> ConversationThread | None: ...

    async def update(self, thread: ConversationThread) -> None: ...


class MessageRepository(Protocol):
    async def append(self, message: Message) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> Message | None: ...

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> Message | None: ...

    async def get_by_external_message_id(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        external_message_id: str,
    ) -> Message | None: ...


class MessageEditEventRepository(Protocol):
    async def append(self, event: MessageEditEvent) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageEditEvent | None: ...

    async def get_for_update(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageEditEvent | None: ...


class MessageDeletionEventRepository(Protocol):
    async def append(self, event: MessageDeletionEvent) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageDeletionEvent | None: ...


class MessageDeliveryStatusEventRepository(Protocol):
    async def append(self, event: MessageDeliveryStatusEvent) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageDeliveryStatusEvent | None: ...


class ManagerAssignmentRepository(Protocol):
    async def append(self, assignment: ManagerAssignment) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        assignment_id: UUID,
    ) -> ManagerAssignment | None: ...


class CRMOutcomeRepository(Protocol):
    async def append(self, outcome: CRMOutcome) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        outcome_id: UUID,
    ) -> CRMOutcome | None: ...


class WebhookEventRepository(Protocol):
    async def append(self, event: WebhookEvent) -> None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> WebhookEvent | None: ...

    async def get_by_external_event_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        external_event_id: str,
    ) -> WebhookEvent | None: ...

    async def update_processing_status(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
        processing_status: WebhookProcessingStatus,
        processed_at: datetime | None,
    ) -> None: ...

    async def attach_encrypted_payload(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
        encrypted_payload_content_id: UUID,
    ) -> None: ...


class CanonicalUnitOfWork(Protocol):
    channel_connections: ChannelConnectionRepository
    leads: LeadRepository
    sales_cases: SalesCaseRepository
    conversation_threads: ConversationThreadRepository
    messages: MessageRepository
    message_edit_events: MessageEditEventRepository
    message_deletion_events: MessageDeletionEventRepository
    message_delivery_status_events: MessageDeliveryStatusEventRepository
    manager_assignments: ManagerAssignmentRepository
    crm_outcomes: CRMOutcomeRepository
    webhook_events: WebhookEventRepository
    audit_events: AuditEventAppendRepository

    async def __aenter__(self) -> CanonicalUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
