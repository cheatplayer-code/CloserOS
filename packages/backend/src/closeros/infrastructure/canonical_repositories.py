"""PostgreSQL repository implementations for canonical conversation entities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.canonical_persistence import (
    CanonicalPersistenceError,
    CanonicalRecordNotFoundError,
    CanonicalReferenceError,
    DuplicateChannelConnectionError,
    DuplicateConversationThreadError,
    DuplicateCRMOutcomeError,
    DuplicateLeadError,
    DuplicateMessageDeletionEventError,
    DuplicateMessageDeliveryStatusEventError,
    DuplicateMessageEditEventError,
    DuplicateMessageError,
    DuplicateWebhookEventError,
)
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
from closeros.infrastructure import canonical_mappers as mappers
from closeros.infrastructure.canonical_orm import (
    ChannelConnectionRow,
    ConversationThreadRow,
    CRMOutcomeRow,
    LeadRow,
    ManagerAssignmentRow,
    MessageDeletionEventRow,
    MessageDeliveryStatusEventRow,
    MessageEditEventRow,
    MessageRow,
    SalesCaseRow,
    WebhookEventRow,
)
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import (
    tenant_scoped_get,
    tenant_scoped_get_required,
)

_CONSTRAINT_ERRORS: dict[str, type[CanonicalPersistenceError]] = {
    "uq_channel_connections_tenant_id_provider_external_connection_id": (
        DuplicateChannelConnectionError
    ),
    "uq_leads_tenant_id_external_identity_id": DuplicateLeadError,
    "uq_conversation_threads_tenant_id_channel_connection_id_external_conversation_id": (
        DuplicateConversationThreadError
    ),
    "uq_messages_tenant_id_conversation_thread_id_external_message_id": DuplicateMessageError,
    "uq_message_edit_events_tenant_id_external_event_id": DuplicateMessageEditEventError,
    "uq_message_deletion_events_tenant_id_external_event_id": DuplicateMessageDeletionEventError,
    "uq_message_delivery_status_events_tenant_id_external_event_id": (
        DuplicateMessageDeliveryStatusEventError
    ),
    "uq_crm_outcomes_tenant_id_external_deal_id": DuplicateCRMOutcomeError,
    "uq_webhook_events_tenant_id_channel_connection_id_external_event_id": (
        DuplicateWebhookEventError
    ),
    "fk_conversation_threads_tenant_id_channel_connection_id_channel_connections": (
        CanonicalReferenceError
    ),
    "fk_conversation_threads_tenant_id_sales_case_id_sales_cases": CanonicalReferenceError,
    "fk_messages_tenant_id_conversation_thread_id_conversation_threads": CanonicalReferenceError,
    "fk_messages_tenant_id_reply_to_message_id_messages": CanonicalReferenceError,
    "fk_message_edit_events_tenant_id_message_id_messages": CanonicalReferenceError,
    "fk_message_deletion_events_tenant_id_message_id_messages": CanonicalReferenceError,
    "fk_message_delivery_status_events_tenant_id_message_id_messages": CanonicalReferenceError,
    "fk_manager_assignments_tenant_id_conversation_thread_id_conversation_threads": (
        CanonicalReferenceError
    ),
    "fk_manager_assignments_tenant_id_sales_case_id_sales_cases": CanonicalReferenceError,
    "fk_crm_outcomes_tenant_id_sales_case_id_sales_cases": CanonicalReferenceError,
    "fk_webhook_events_tenant_id_channel_connection_id_channel_connections": (
        CanonicalReferenceError
    ),
}


def _translate_integrity_error(error: IntegrityError) -> CanonicalPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=CanonicalPersistenceError,
        message="canonical persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyChannelConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, connection: ChannelConnection) -> None:
        self._session.add(mappers.channel_connection_to_row(connection))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> ChannelConnection | None:
        row = await tenant_scoped_get(
            self._session,
            ChannelConnectionRow,
            tenant_id=tenant_id,
            record_id=connection_id,
        )
        return None if row is None else mappers.channel_connection_to_domain(row)

    async def get_by_provider_external_id(
        self,
        *,
        tenant_id: UUID,
        provider: ProviderKind,
        external_connection_id: str,
    ) -> ChannelConnection | None:
        row = (
            await self._session.execute(
                select(ChannelConnectionRow).where(
                    ChannelConnectionRow.tenant_id == tenant_id,
                    ChannelConnectionRow.provider == provider.value,
                    ChannelConnectionRow.external_connection_id == external_connection_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.channel_connection_to_domain(row)

    async def update(self, connection: ChannelConnection) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            ChannelConnectionRow,
            tenant_id=connection.tenant_id,
            record_id=connection.id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="channel connection not found",
        )
        mappers.update_channel_connection_row(row, connection)
        await _flush(self._session)


class SqlAlchemyLeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, lead: Lead) -> None:
        self._session.add(mappers.lead_to_row(lead))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        lead_id: UUID,
    ) -> Lead | None:
        row = await tenant_scoped_get(
            self._session,
            LeadRow,
            tenant_id=tenant_id,
            record_id=lead_id,
        )
        return None if row is None else mappers.lead_to_domain(row)

    async def get_by_external_identity_id(
        self,
        *,
        tenant_id: UUID,
        external_identity_id: str,
    ) -> Lead | None:
        row = (
            await self._session.execute(
                select(LeadRow).where(
                    LeadRow.tenant_id == tenant_id,
                    LeadRow.external_identity_id == external_identity_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.lead_to_domain(row)

    async def update(self, lead: Lead) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            LeadRow,
            tenant_id=lead.tenant_id,
            record_id=lead.id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="lead not found",
        )
        mappers.update_lead_row(row, lead)
        await _flush(self._session)


class SqlAlchemySalesCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, sales_case: SalesCase) -> None:
        self._session.add(mappers.sales_case_to_row(sales_case))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        sales_case_id: UUID,
    ) -> SalesCase | None:
        row = await tenant_scoped_get(
            self._session,
            SalesCaseRow,
            tenant_id=tenant_id,
            record_id=sales_case_id,
        )
        return None if row is None else mappers.sales_case_to_domain(row)

    async def update(self, sales_case: SalesCase) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            SalesCaseRow,
            tenant_id=sales_case.tenant_id,
            record_id=sales_case.id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="sales case not found",
        )
        mappers.update_sales_case_row(row, sales_case)
        await _flush(self._session)


class SqlAlchemyConversationThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, thread: ConversationThread) -> None:
        self._session.add(mappers.conversation_thread_to_row(thread))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> ConversationThread | None:
        row = await tenant_scoped_get(
            self._session,
            ConversationThreadRow,
            tenant_id=tenant_id,
            record_id=thread_id,
        )
        return None if row is None else mappers.conversation_thread_to_domain(row)

    async def get_by_external_conversation_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        external_conversation_id: str,
    ) -> ConversationThread | None:
        row = (
            await self._session.execute(
                select(ConversationThreadRow).where(
                    ConversationThreadRow.tenant_id == tenant_id,
                    ConversationThreadRow.channel_connection_id == channel_connection_id,
                    ConversationThreadRow.external_conversation_id == external_conversation_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.conversation_thread_to_domain(row)

    async def update(self, thread: ConversationThread) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            ConversationThreadRow,
            tenant_id=thread.tenant_id,
            record_id=thread.id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="conversation thread not found",
        )
        mappers.update_conversation_thread_row(row, thread)
        await _flush(self._session)


class SqlAlchemyMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, message: Message) -> None:
        self._session.add(mappers.message_to_row(message))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> Message | None:
        row = await tenant_scoped_get(
            self._session,
            MessageRow,
            tenant_id=tenant_id,
            record_id=message_id,
        )
        return None if row is None else mappers.message_to_domain(row)

    async def get_by_external_message_id(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        external_message_id: str,
    ) -> Message | None:
        row = (
            await self._session.execute(
                select(MessageRow).where(
                    MessageRow.tenant_id == tenant_id,
                    MessageRow.conversation_thread_id == conversation_thread_id,
                    MessageRow.external_message_id == external_message_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.message_to_domain(row)


class SqlAlchemyMessageEditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: MessageEditEvent) -> None:
        self._session.add(mappers.message_edit_event_to_row(event))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageEditEvent | None:
        row = await tenant_scoped_get(
            self._session,
            MessageEditEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
        )
        return None if row is None else mappers.message_edit_event_to_domain(row)


class SqlAlchemyMessageDeletionEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: MessageDeletionEvent) -> None:
        self._session.add(mappers.message_deletion_event_to_row(event))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageDeletionEvent | None:
        row = await tenant_scoped_get(
            self._session,
            MessageDeletionEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
        )
        return None if row is None else mappers.message_deletion_event_to_domain(row)


class SqlAlchemyMessageDeliveryStatusEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: MessageDeliveryStatusEvent) -> None:
        self._session.add(mappers.message_delivery_status_event_to_row(event))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> MessageDeliveryStatusEvent | None:
        row = await tenant_scoped_get(
            self._session,
            MessageDeliveryStatusEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
        )
        return None if row is None else mappers.message_delivery_status_event_to_domain(row)


class SqlAlchemyManagerAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, assignment: ManagerAssignment) -> None:
        self._session.add(mappers.manager_assignment_to_row(assignment))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        assignment_id: UUID,
    ) -> ManagerAssignment | None:
        row = await tenant_scoped_get(
            self._session,
            ManagerAssignmentRow,
            tenant_id=tenant_id,
            record_id=assignment_id,
        )
        return None if row is None else mappers.manager_assignment_to_domain(row)


class SqlAlchemyCRMOutcomeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, outcome: CRMOutcome) -> None:
        self._session.add(mappers.crm_outcome_to_row(outcome))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        outcome_id: UUID,
    ) -> CRMOutcome | None:
        row = await tenant_scoped_get(
            self._session,
            CRMOutcomeRow,
            tenant_id=tenant_id,
            record_id=outcome_id,
        )
        return None if row is None else mappers.crm_outcome_to_domain(row)


class SqlAlchemyWebhookEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: WebhookEvent) -> None:
        self._session.add(mappers.webhook_event_to_row(event))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
    ) -> WebhookEvent | None:
        row = await tenant_scoped_get(
            self._session,
            WebhookEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
        )
        return None if row is None else mappers.webhook_event_to_domain(row)

    async def get_by_external_event_id(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        external_event_id: str,
    ) -> WebhookEvent | None:
        row = (
            await self._session.execute(
                select(WebhookEventRow).where(
                    WebhookEventRow.tenant_id == tenant_id,
                    WebhookEventRow.channel_connection_id == channel_connection_id,
                    WebhookEventRow.external_event_id == external_event_id,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.webhook_event_to_domain(row)

    async def update_processing_status(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
        processing_status: WebhookProcessingStatus,
        processed_at: datetime | None,
    ) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            WebhookEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="webhook event not found",
        )
        row.processing_status = processing_status.value
        row.processed_at = processed_at
        await _flush(self._session)

    async def attach_encrypted_payload(
        self,
        *,
        tenant_id: UUID,
        event_id: UUID,
        encrypted_payload_content_id: UUID,
    ) -> None:
        row = await tenant_scoped_get_required(
            self._session,
            WebhookEventRow,
            tenant_id=tenant_id,
            record_id=event_id,
            not_found_error=CanonicalRecordNotFoundError,
            not_found_message="webhook event not found",
        )
        row.encrypted_payload_content_id = encrypted_payload_content_id
        await _flush(self._session)
