"""Synthetic fixtures for canonical persistence integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.domain.adapter_metadata import AdapterMetadata
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

from tests.tenant_persistence_support import TENANT_A_ID, USER_ID

CHANNEL_CONNECTION_A_ID = UUID("00000000-0000-0000-0000-000000000100")
CHANNEL_CONNECTION_B_ID = UUID("00000000-0000-0000-0000-000000000101")
LEAD_A_ID = UUID("00000000-0000-0000-0000-000000000200")
SALES_CASE_A_ID = UUID("00000000-0000-0000-0000-000000000300")
THREAD_A_ID = UUID("00000000-0000-0000-0000-000000000400")
MESSAGE_A_ID = UUID("00000000-0000-0000-0000-000000000500")
MESSAGE_B_ID = UUID("00000000-0000-0000-0000-000000000501")
EDIT_EVENT_A_ID = UUID("00000000-0000-0000-0000-000000000600")
DELETION_EVENT_A_ID = UUID("00000000-0000-0000-0000-000000000601")
DELIVERY_EVENT_A_ID = UUID("00000000-0000-0000-0000-000000000602")
ASSIGNMENT_A_ID = UUID("00000000-0000-0000-0000-000000000700")
CRM_OUTCOME_A_ID = UUID("00000000-0000-0000-0000-000000000800")
WEBHOOK_EVENT_A_ID = UUID("00000000-0000-0000-0000-000000000900")
CONTENT_A_ID = UUID("00000000-0000-0000-0000-000000000a00")
CONTENT_B_ID = UUID("00000000-0000-0000-0000-000000000a01")

NOW = datetime(2026, 7, 12, 9, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
EVEN_LATER = NOW + timedelta(minutes=10)


def synthetic_adapter_metadata(**entries: str | int | bool | None) -> AdapterMetadata:
    return AdapterMetadata.from_mapping(entries or {"provider_ref": "synthetic-ref-001"})


def synthetic_channel_connection(
    *,
    connection_id: UUID = CHANNEL_CONNECTION_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    provider: ProviderKind = ProviderKind.WHATSAPP,
    external_connection_id: str = "wa-conn-synthetic-001",
    status: ChannelConnectionStatus = ChannelConnectionStatus.ACTIVE,
) -> ChannelConnection:
    return ChannelConnection(
        id=connection_id,
        tenant_id=tenant_id,
        provider=provider,
        external_connection_id=external_connection_id,
        status=status,
        adapter_metadata=synthetic_adapter_metadata(),
        created_at=NOW,
        updated_at=NOW,
    )


def synthetic_lead(
    *,
    lead_id: UUID = LEAD_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    external_identity_id: str = "lead-synthetic-001",
    status: LeadStatus = LeadStatus.ACTIVE,
) -> Lead:
    return Lead(
        id=lead_id,
        tenant_id=tenant_id,
        external_identity_id=external_identity_id,
        status=status,
        adapter_metadata=synthetic_adapter_metadata(),
        created_at=NOW,
        updated_at=NOW,
    )


def synthetic_sales_case(
    *,
    sales_case_id: UUID = SALES_CASE_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    status: SalesCaseStatus = SalesCaseStatus.NEW,
) -> SalesCase:
    return SalesCase(
        id=sales_case_id,
        tenant_id=tenant_id,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def synthetic_conversation_thread(
    *,
    thread_id: UUID = THREAD_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    channel_connection_id: UUID = CHANNEL_CONNECTION_A_ID,
    external_conversation_id: str = "thread-synthetic-001",
    sales_case_id: UUID | None = None,
    lifecycle_status: SalesCaseStatus | None = SalesCaseStatus.AWAITING_CUSTOMER,
) -> ConversationThread:
    if sales_case_id is not None:
        lifecycle_status = None
    return ConversationThread(
        id=thread_id,
        tenant_id=tenant_id,
        channel_connection_id=channel_connection_id,
        external_conversation_id=external_conversation_id,
        sales_case_id=sales_case_id,
        lifecycle_status=lifecycle_status,
        adapter_metadata=synthetic_adapter_metadata(),
        created_at=NOW,
        updated_at=NOW,
    )


def synthetic_message(
    *,
    message_id: UUID = MESSAGE_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    conversation_thread_id: UUID = THREAD_A_ID,
    external_message_id: str = "msg-synthetic-001",
    content_id: UUID | None = CONTENT_A_ID,
    reply_to_message_id: UUID | None = None,
    sender_type: ParticipantSenderType = ParticipantSenderType.CUSTOMER,
    direction: MessageDirection = MessageDirection.INBOUND,
    sent_at: datetime = NOW,
    received_at: datetime = LATER,
) -> Message:
    return Message(
        id=message_id,
        tenant_id=tenant_id,
        conversation_thread_id=conversation_thread_id,
        external_message_id=external_message_id,
        sender_type=sender_type,
        direction=direction,
        sent_at=sent_at,
        received_at=received_at,
        content_id=content_id,
        reply_to_message_id=reply_to_message_id,
        adapter_metadata=synthetic_adapter_metadata(),
    )


def synthetic_message_edit_event(
    *,
    event_id: UUID = EDIT_EVENT_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    message_id: UUID = MESSAGE_A_ID,
    external_event_id: str = "edit-synthetic-001",
    content_id: UUID | None = CONTENT_B_ID,
    occurred_at: datetime = EVEN_LATER,
) -> MessageEditEvent:
    return MessageEditEvent(
        id=event_id,
        tenant_id=tenant_id,
        message_id=message_id,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        content_id=content_id,
        adapter_metadata=synthetic_adapter_metadata(),
    )


def synthetic_message_deletion_event(
    *,
    event_id: UUID = DELETION_EVENT_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    message_id: UUID = MESSAGE_A_ID,
    external_event_id: str = "delete-synthetic-001",
    occurred_at: datetime = EVEN_LATER,
) -> MessageDeletionEvent:
    return MessageDeletionEvent(
        id=event_id,
        tenant_id=tenant_id,
        message_id=message_id,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        adapter_metadata=synthetic_adapter_metadata(),
    )


def synthetic_message_delivery_status_event(
    *,
    event_id: UUID = DELIVERY_EVENT_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    message_id: UUID = MESSAGE_A_ID,
    external_event_id: str = "delivery-synthetic-001",
    delivery_status: DeliveryStatus = DeliveryStatus.DELIVERED,
    occurred_at: datetime = EVEN_LATER,
) -> MessageDeliveryStatusEvent:
    return MessageDeliveryStatusEvent(
        id=event_id,
        tenant_id=tenant_id,
        message_id=message_id,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        delivery_status=delivery_status,
        adapter_metadata=synthetic_adapter_metadata(),
    )


def synthetic_manager_assignment(
    *,
    assignment_id: UUID = ASSIGNMENT_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    manager_user_id: UUID = USER_ID,
    conversation_thread_id: UUID | None = THREAD_A_ID,
    sales_case_id: UUID | None = None,
) -> ManagerAssignment:
    return ManagerAssignment(
        id=assignment_id,
        tenant_id=tenant_id,
        manager_user_id=manager_user_id,
        conversation_thread_id=conversation_thread_id,
        sales_case_id=sales_case_id,
        assigned_at=NOW,
    )


def synthetic_crm_outcome(
    *,
    outcome_id: UUID = CRM_OUTCOME_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    sales_case_id: UUID = SALES_CASE_A_ID,
    external_deal_id: str = "deal-synthetic-001",
    outcome_type: CrmOutcomeType = CrmOutcomeType.WON,
) -> CRMOutcome:
    return CRMOutcome(
        id=outcome_id,
        tenant_id=tenant_id,
        sales_case_id=sales_case_id,
        external_deal_id=external_deal_id,
        outcome_type=outcome_type,
        occurred_at=NOW,
        adapter_metadata=synthetic_adapter_metadata(),
    )


def synthetic_webhook_event(
    *,
    event_id: UUID = WEBHOOK_EVENT_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    channel_connection_id: UUID = CHANNEL_CONNECTION_A_ID,
    external_event_id: str = "webhook-synthetic-001",
    processing_status: WebhookProcessingStatus = WebhookProcessingStatus.RECEIVED,
    processed_at: datetime | None = None,
) -> WebhookEvent:
    return WebhookEvent(
        id=event_id,
        tenant_id=tenant_id,
        channel_connection_id=channel_connection_id,
        external_event_id=external_event_id,
        processing_status=processing_status,
        received_at=NOW,
        processed_at=processed_at,
        encrypted_payload_content_id=None,
        adapter_metadata=synthetic_adapter_metadata(),
    )
