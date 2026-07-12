"""Explicit mapping between canonical ORM rows and domain objects."""

from __future__ import annotations

from closeros.domain.adapter_metadata import AdapterMetadata, AdapterScalar
from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    CrmOutcomeType,
    DeliveryStatus,
    LeadStatus,
    MessageDirection,
    ParticipantSenderType,
    ProviderKind,
    SalesCaseStatus,
    WebhookProcessingStatus,
)
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


def adapter_metadata_to_json(metadata: AdapterMetadata) -> dict[str, object]:
    return dict(metadata.as_dict())


def adapter_metadata_from_json(value: object) -> AdapterMetadata:
    if not isinstance(value, dict):
        raise TypeError("adapter_metadata must be a dict")

    normalized: dict[str, AdapterScalar] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            raise TypeError("adapter_metadata keys must be strings")
        if raw_value is None or isinstance(raw_value, (bool, int, str)):
            normalized[key] = raw_value
        else:
            raise TypeError("adapter_metadata values must be JSON scalars")

    return AdapterMetadata.from_mapping(normalized)


def channel_connection_to_row(connection: ChannelConnection) -> ChannelConnectionRow:
    return ChannelConnectionRow(
        id=connection.id,
        tenant_id=connection.tenant_id,
        provider=connection.provider.value,
        external_connection_id=connection.external_connection_id,
        status=connection.status.value,
        adapter_metadata=adapter_metadata_to_json(connection.adapter_metadata),
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def channel_connection_to_domain(row: ChannelConnectionRow) -> ChannelConnection:
    return ChannelConnection(
        id=row.id,
        tenant_id=row.tenant_id,
        provider=ProviderKind(row.provider),
        external_connection_id=row.external_connection_id,
        status=ChannelConnectionStatus(row.status),
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_channel_connection_row(
    row: ChannelConnectionRow,
    connection: ChannelConnection,
) -> None:
    row.provider = connection.provider.value
    row.external_connection_id = connection.external_connection_id
    row.status = connection.status.value
    row.adapter_metadata = adapter_metadata_to_json(connection.adapter_metadata)
    row.updated_at = connection.updated_at


def lead_to_row(lead: Lead) -> LeadRow:
    return LeadRow(
        id=lead.id,
        tenant_id=lead.tenant_id,
        external_identity_id=lead.external_identity_id,
        status=lead.status.value,
        adapter_metadata=adapter_metadata_to_json(lead.adapter_metadata),
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def lead_to_domain(row: LeadRow) -> Lead:
    return Lead(
        id=row.id,
        tenant_id=row.tenant_id,
        external_identity_id=row.external_identity_id,
        status=LeadStatus(row.status),
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_lead_row(row: LeadRow, lead: Lead) -> None:
    row.external_identity_id = lead.external_identity_id
    row.status = lead.status.value
    row.adapter_metadata = adapter_metadata_to_json(lead.adapter_metadata)
    row.updated_at = lead.updated_at


def sales_case_to_row(sales_case: SalesCase) -> SalesCaseRow:
    return SalesCaseRow(
        id=sales_case.id,
        tenant_id=sales_case.tenant_id,
        status=sales_case.status.value,
        created_at=sales_case.created_at,
        updated_at=sales_case.updated_at,
    )


def sales_case_to_domain(row: SalesCaseRow) -> SalesCase:
    return SalesCase(
        id=row.id,
        tenant_id=row.tenant_id,
        status=SalesCaseStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_sales_case_row(row: SalesCaseRow, sales_case: SalesCase) -> None:
    row.status = sales_case.status.value
    row.updated_at = sales_case.updated_at


def conversation_thread_to_row(thread: ConversationThread) -> ConversationThreadRow:
    return ConversationThreadRow(
        id=thread.id,
        tenant_id=thread.tenant_id,
        channel_connection_id=thread.channel_connection_id,
        external_conversation_id=thread.external_conversation_id,
        sales_case_id=thread.sales_case_id,
        lifecycle_status=(
            None if thread.lifecycle_status is None else thread.lifecycle_status.value
        ),
        adapter_metadata=adapter_metadata_to_json(thread.adapter_metadata),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def conversation_thread_to_domain(row: ConversationThreadRow) -> ConversationThread:
    return ConversationThread(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_connection_id=row.channel_connection_id,
        external_conversation_id=row.external_conversation_id,
        sales_case_id=row.sales_case_id,
        lifecycle_status=(
            None if row.lifecycle_status is None else SalesCaseStatus(row.lifecycle_status)
        ),
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_conversation_thread_row(
    row: ConversationThreadRow,
    thread: ConversationThread,
) -> None:
    row.channel_connection_id = thread.channel_connection_id
    row.external_conversation_id = thread.external_conversation_id
    row.sales_case_id = thread.sales_case_id
    row.lifecycle_status = (
        None if thread.lifecycle_status is None else thread.lifecycle_status.value
    )
    row.adapter_metadata = adapter_metadata_to_json(thread.adapter_metadata)
    row.updated_at = thread.updated_at


def message_to_row(message: Message) -> MessageRow:
    return MessageRow(
        id=message.id,
        tenant_id=message.tenant_id,
        conversation_thread_id=message.conversation_thread_id,
        external_message_id=message.external_message_id,
        sender_type=message.sender_type.value,
        direction=message.direction.value,
        sent_at=message.sent_at,
        received_at=message.received_at,
        content_id=message.content_id,
        reply_to_message_id=message.reply_to_message_id,
        adapter_metadata=adapter_metadata_to_json(message.adapter_metadata),
    )


def message_to_domain(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        external_message_id=row.external_message_id,
        sender_type=ParticipantSenderType(row.sender_type),
        direction=MessageDirection(row.direction),
        sent_at=row.sent_at,
        received_at=row.received_at,
        content_id=row.content_id,
        reply_to_message_id=row.reply_to_message_id,
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )


def message_edit_event_to_row(event: MessageEditEvent) -> MessageEditEventRow:
    return MessageEditEventRow(
        id=event.id,
        tenant_id=event.tenant_id,
        message_id=event.message_id,
        external_event_id=event.external_event_id,
        occurred_at=event.occurred_at,
        content_id=event.content_id,
        adapter_metadata=adapter_metadata_to_json(event.adapter_metadata),
    )


def message_edit_event_to_domain(row: MessageEditEventRow) -> MessageEditEvent:
    return MessageEditEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        message_id=row.message_id,
        external_event_id=row.external_event_id,
        occurred_at=row.occurred_at,
        content_id=row.content_id,
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )


def message_deletion_event_to_row(event: MessageDeletionEvent) -> MessageDeletionEventRow:
    return MessageDeletionEventRow(
        id=event.id,
        tenant_id=event.tenant_id,
        message_id=event.message_id,
        external_event_id=event.external_event_id,
        occurred_at=event.occurred_at,
        adapter_metadata=adapter_metadata_to_json(event.adapter_metadata),
    )


def message_deletion_event_to_domain(row: MessageDeletionEventRow) -> MessageDeletionEvent:
    return MessageDeletionEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        message_id=row.message_id,
        external_event_id=row.external_event_id,
        occurred_at=row.occurred_at,
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )


def message_delivery_status_event_to_row(
    event: MessageDeliveryStatusEvent,
) -> MessageDeliveryStatusEventRow:
    return MessageDeliveryStatusEventRow(
        id=event.id,
        tenant_id=event.tenant_id,
        message_id=event.message_id,
        external_event_id=event.external_event_id,
        occurred_at=event.occurred_at,
        delivery_status=event.delivery_status.value,
        adapter_metadata=adapter_metadata_to_json(event.adapter_metadata),
    )


def message_delivery_status_event_to_domain(
    row: MessageDeliveryStatusEventRow,
) -> MessageDeliveryStatusEvent:
    return MessageDeliveryStatusEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        message_id=row.message_id,
        external_event_id=row.external_event_id,
        occurred_at=row.occurred_at,
        delivery_status=DeliveryStatus(row.delivery_status),
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )


def manager_assignment_to_row(assignment: ManagerAssignment) -> ManagerAssignmentRow:
    return ManagerAssignmentRow(
        id=assignment.id,
        tenant_id=assignment.tenant_id,
        manager_user_id=assignment.manager_user_id,
        conversation_thread_id=assignment.conversation_thread_id,
        sales_case_id=assignment.sales_case_id,
        assigned_at=assignment.assigned_at,
    )


def manager_assignment_to_domain(row: ManagerAssignmentRow) -> ManagerAssignment:
    return ManagerAssignment(
        id=row.id,
        tenant_id=row.tenant_id,
        manager_user_id=row.manager_user_id,
        conversation_thread_id=row.conversation_thread_id,
        sales_case_id=row.sales_case_id,
        assigned_at=row.assigned_at,
    )


def crm_outcome_to_row(outcome: CRMOutcome) -> CRMOutcomeRow:
    return CRMOutcomeRow(
        id=outcome.id,
        tenant_id=outcome.tenant_id,
        sales_case_id=outcome.sales_case_id,
        external_deal_id=outcome.external_deal_id,
        outcome_type=outcome.outcome_type.value,
        occurred_at=outcome.occurred_at,
        adapter_metadata=adapter_metadata_to_json(outcome.adapter_metadata),
    )


def crm_outcome_to_domain(row: CRMOutcomeRow) -> CRMOutcome:
    return CRMOutcome(
        id=row.id,
        tenant_id=row.tenant_id,
        sales_case_id=row.sales_case_id,
        external_deal_id=row.external_deal_id,
        outcome_type=CrmOutcomeType(row.outcome_type),
        occurred_at=row.occurred_at,
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )


def webhook_event_to_row(event: WebhookEvent) -> WebhookEventRow:
    return WebhookEventRow(
        id=event.id,
        tenant_id=event.tenant_id,
        channel_connection_id=event.channel_connection_id,
        external_event_id=event.external_event_id,
        processing_status=event.processing_status.value,
        received_at=event.received_at,
        processed_at=event.processed_at,
        encrypted_payload_content_id=event.encrypted_payload_content_id,
        adapter_metadata=adapter_metadata_to_json(event.adapter_metadata),
    )


def webhook_event_to_domain(row: WebhookEventRow) -> WebhookEvent:
    return WebhookEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_connection_id=row.channel_connection_id,
        external_event_id=row.external_event_id,
        processing_status=WebhookProcessingStatus(row.processing_status),
        received_at=row.received_at,
        processed_at=row.processed_at,
        encrypted_payload_content_id=row.encrypted_payload_content_id,
        adapter_metadata=adapter_metadata_from_json(row.adapter_metadata),
    )
