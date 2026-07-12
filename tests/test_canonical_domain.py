"""Domain invariant tests for canonical conversation entities."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    LeadStatus,
    MessageDirection,
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
    MessageDeliveryStatusEvent,
    MessageEditEvent,
)
from closeros.domain.sales_case import SalesCase
from closeros.domain.webhook_event import WebhookEvent

from tests.canonical_persistence_support import (
    CHANNEL_CONNECTION_A_ID,
    CONTENT_A_ID,
    MESSAGE_A_ID,
    SALES_CASE_A_ID,
    THREAD_A_ID,
    synthetic_adapter_metadata,
    synthetic_channel_connection,
    synthetic_conversation_thread,
    synthetic_crm_outcome,
    synthetic_lead,
    synthetic_manager_assignment,
    synthetic_message,
    synthetic_message_deletion_event,
    synthetic_webhook_event,
)
from tests.tenant_persistence_support import TENANT_A_ID, USER_ID

NOW = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def test_adapter_metadata_accepts_safe_scalar_entries() -> None:
    metadata = AdapterMetadata.from_mapping({"provider_ref": "ref-001", "retry_count": 2})

    assert metadata.as_dict() == {"provider_ref": "ref-001", "retry_count": 2}


def test_adapter_metadata_rejects_sensitive_key_fragments() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        AdapterMetadata.from_mapping({"access_token": "secret-value"})


def test_adapter_metadata_rejects_nested_values() -> None:
    with pytest.raises(ValueError, match="JSON scalar"):
        AdapterMetadata.from_mapping({"provider_ref": {"nested": "value"}})


def test_adapter_metadata_rejects_empty_string_values() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        AdapterMetadata.from_mapping({"provider_ref": ""})


def test_adapter_metadata_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        AdapterMetadata.from_mapping({"provider_ref": "a", "provider_ref ": "b"})


def test_channel_connection_normalizes_external_connection_id() -> None:
    connection = synthetic_channel_connection(external_connection_id="  wa-001  ")

    assert connection.external_connection_id == "wa-001"


def test_channel_connection_rejects_updated_at_before_created_at() -> None:
    with pytest.raises(ValueError, match="updated_at"):
        ChannelConnection(
            id=CHANNEL_CONNECTION_A_ID,
            tenant_id=TENANT_A_ID,
            provider=ProviderKind.WHATSAPP,
            external_connection_id="wa-001",
            status=ChannelConnectionStatus.ACTIVE,
            adapter_metadata=synthetic_adapter_metadata(),
            created_at=LATER,
            updated_at=NOW,
        )


def test_lead_requires_lead_status_enum() -> None:
    with pytest.raises(TypeError, match="LeadStatus"):
        Lead(
            id=UUID("00000000-0000-0000-0000-000000000200"),
            tenant_id=TENANT_A_ID,
            external_identity_id="lead-001",
            status="active",  # type: ignore[arg-type]
            adapter_metadata=synthetic_adapter_metadata(),
            created_at=NOW,
            updated_at=NOW,
        )


def test_sales_case_rejects_non_uuid_id() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        SalesCase(
            id="not-a-uuid",  # type: ignore[arg-type]
            tenant_id=TENANT_A_ID,
            status=SalesCaseStatus.NEW,
            created_at=NOW,
            updated_at=NOW,
        )


def test_conversation_thread_rejects_lifecycle_with_sales_case() -> None:
    with pytest.raises(ValueError, match="lifecycle_status must be omitted"):
        ConversationThread(
            id=THREAD_A_ID,
            tenant_id=TENANT_A_ID,
            channel_connection_id=CHANNEL_CONNECTION_A_ID,
            external_conversation_id="thread-001",
            sales_case_id=SALES_CASE_A_ID,
            lifecycle_status=SalesCaseStatus.NEW,
            adapter_metadata=synthetic_adapter_metadata(),
            created_at=NOW,
            updated_at=NOW,
        )


def test_message_rejects_received_at_before_sent_at() -> None:
    with pytest.raises(ValueError, match="received_at"):
        synthetic_message(sent_at=LATER, received_at=NOW)


def test_message_edit_event_requires_adapter_metadata_type() -> None:
    with pytest.raises(TypeError, match="AdapterMetadata"):
        MessageEditEvent(
            id=UUID("00000000-0000-0000-0000-000000000600"),
            tenant_id=TENANT_A_ID,
            message_id=MESSAGE_A_ID,
            external_event_id="edit-001",
            occurred_at=NOW,
            content_id=CONTENT_A_ID,
            adapter_metadata=cast(Any, {"provider_ref": "x"}),
        )


def test_message_deletion_event_strips_external_event_id() -> None:
    event = synthetic_message_deletion_event(external_event_id="  delete-001  ")

    assert event.external_event_id == "delete-001"


def test_message_delivery_status_event_requires_delivery_status_enum() -> None:
    with pytest.raises(TypeError, match="DeliveryStatus"):
        MessageDeliveryStatusEvent(
            id=UUID("00000000-0000-0000-0000-000000000602"),
            tenant_id=TENANT_A_ID,
            message_id=MESSAGE_A_ID,
            external_event_id="delivery-001",
            occurred_at=NOW,
            delivery_status="delivered",  # type: ignore[arg-type]
            adapter_metadata=synthetic_adapter_metadata(),
        )


def test_manager_assignment_requires_exactly_one_target() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ManagerAssignment(
            id=UUID("00000000-0000-0000-0000-000000000700"),
            tenant_id=TENANT_A_ID,
            manager_user_id=USER_ID,
            conversation_thread_id=THREAD_A_ID,
            sales_case_id=SALES_CASE_A_ID,
            assigned_at=NOW,
        )


def test_manager_assignment_accepts_sales_case_target() -> None:
    assignment = synthetic_manager_assignment(
        conversation_thread_id=None,
        sales_case_id=SALES_CASE_A_ID,
    )

    assert assignment.sales_case_id == SALES_CASE_A_ID
    assert assignment.conversation_thread_id is None


def test_crm_outcome_normalizes_external_deal_id() -> None:
    outcome = synthetic_crm_outcome(external_deal_id="  deal-001  ")

    assert outcome.external_deal_id == "deal-001"


def test_crm_outcome_requires_crm_outcome_type_enum() -> None:
    with pytest.raises(TypeError, match="CrmOutcomeType"):
        CRMOutcome(
            id=UUID("00000000-0000-0000-0000-000000000800"),
            tenant_id=TENANT_A_ID,
            sales_case_id=SALES_CASE_A_ID,
            external_deal_id="deal-001",
            outcome_type="won",  # type: ignore[arg-type]
            occurred_at=NOW,
            adapter_metadata=synthetic_adapter_metadata(),
        )


def test_webhook_event_rejects_processed_at_before_received_at() -> None:
    with pytest.raises(ValueError, match="processed_at"):
        WebhookEvent(
            id=UUID("00000000-0000-0000-0000-000000000900"),
            tenant_id=TENANT_A_ID,
            channel_connection_id=CHANNEL_CONNECTION_A_ID,
            external_event_id="webhook-001",
            processing_status=WebhookProcessingStatus.PROCESSED,
            received_at=LATER,
            processed_at=NOW,
            encrypted_payload_content_id=None,
            adapter_metadata=synthetic_adapter_metadata(),
        )


def test_webhook_event_accepts_null_processed_at() -> None:
    event = synthetic_webhook_event(processed_at=None)

    assert event.processed_at is None


def test_message_requires_participant_sender_type_enum() -> None:
    with pytest.raises(TypeError, match="ParticipantSenderType"):
        Message(
            id=MESSAGE_A_ID,
            tenant_id=TENANT_A_ID,
            conversation_thread_id=THREAD_A_ID,
            external_message_id="msg-001",
            sender_type="customer",  # type: ignore[arg-type]
            direction=MessageDirection.INBOUND,
            sent_at=NOW,
            received_at=LATER,
            content_id=CONTENT_A_ID,
            reply_to_message_id=None,
            adapter_metadata=synthetic_adapter_metadata(),
        )


def test_lead_status_active_is_accepted() -> None:
    lead = synthetic_lead(status=LeadStatus.ACTIVE)

    assert lead.status is LeadStatus.ACTIVE


def test_conversation_thread_without_sales_case_keeps_lifecycle_status() -> None:
    thread = synthetic_conversation_thread(
        sales_case_id=None,
        lifecycle_status=SalesCaseStatus.QUALIFIED,
    )

    assert thread.lifecycle_status is SalesCaseStatus.QUALIFIED


def test_adapter_metadata_empty_mapping_is_allowed() -> None:
    metadata = AdapterMetadata.from_mapping({})

    assert metadata.is_empty is True
