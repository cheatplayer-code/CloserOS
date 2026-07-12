"""Domain tests for WhatsApp Cloud connection invariants and messaging policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.outbound_message import (
    OutboundMessage,
    OutboundMessageKind,
    OutboundMessageStatus,
    OutboundMessageTransitionError,
    outbound_resend_prohibited,
    outbound_send_may_proceed,
    validate_outbound_message_transition,
)
from closeros.domain.provider_capability import ProviderCapability
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnection,
    WhatsAppCloudConnectionError,
    WhatsAppCloudConnectionStatus,
    connection_allows_ingestion,
    connection_allows_outbound,
    connection_requires_credentials,
)
from closeros.domain.whatsapp_messaging_policy import (
    MessagingPolicyViolation,
    WhatsAppMessagingPolicy,
    WhatsAppMessagingPolicyError,
)

from tests.tenant_persistence_support import TENANT_A_ID
from tests.vw_support import (
    GRAPH_API_VERSION,
    VW_CHANNEL_CONNECTION_ID,
    VW_WHATSAPP_CONNECTION_ID,
    vw_whatsapp_connection,
)

_NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)
_CONTENT_ID = UUID("00000000-0000-0000-0000-000000000165")
_THREAD_ID = UUID("00000000-0000-0000-0000-000000000166")
_USER_ID = UUID("00000000-0000-0000-0000-000000000010")


def _outbound_message(*, status: OutboundMessageStatus) -> OutboundMessage:
    approved_by = _USER_ID if status is not OutboundMessageStatus.DRAFT else None
    approved_at = _NOW if approved_by is not None else None
    queued_at = (
        _NOW if status in {OutboundMessageStatus.QUEUED, OutboundMessageStatus.SENDING} else None
    )
    sent_at = _NOW if status is OutboundMessageStatus.SENDING else None
    completed_at = (
        _NOW
        if status
        in {
            OutboundMessageStatus.PROVIDER_ACCEPTED,
            OutboundMessageStatus.DELIVERY_UNKNOWN,
            OutboundMessageStatus.DELIVERED,
            OutboundMessageStatus.READ,
            OutboundMessageStatus.FAILED,
        }
        else None
    )
    failure_code = "provider_failed" if status is OutboundMessageStatus.FAILED else None
    return OutboundMessage(
        id=UUID("00000000-0000-0000-0000-000000000167"),
        tenant_id=TENANT_A_ID,
        conversation_thread_id=_THREAD_ID,
        channel_connection_id=VW_CHANNEL_CONNECTION_ID,
        kind=OutboundMessageKind.FREE_FORM_TEXT,
        status=status,
        encrypted_content_id=_CONTENT_ID,
        provider_template_id=None,
        created_by_user_id=_USER_ID,
        approved_by_user_id=approved_by,
        provider_message_id="wamid.sent"
        if status is OutboundMessageStatus.PROVIDER_ACCEPTED
        else None,
        failure_code=failure_code,
        created_at=_NOW,
        approved_at=approved_at,
        queued_at=queued_at,
        sent_at=sent_at,
        completed_at=completed_at,
        updated_at=_NOW,
        version=1,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (WhatsAppCloudConnectionStatus.ACTIVE, True),
        (WhatsAppCloudConnectionStatus.VERIFICATION_PENDING, True),
        (WhatsAppCloudConnectionStatus.DEGRADED, True),
        (WhatsAppCloudConnectionStatus.DRAFT, False),
        (WhatsAppCloudConnectionStatus.DISABLED, False),
    ],
)
def test_connection_allows_ingestion(status: WhatsAppCloudConnectionStatus, expected: bool) -> None:
    assert connection_allows_ingestion(status) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (WhatsAppCloudConnectionStatus.ACTIVE, True),
        (WhatsAppCloudConnectionStatus.VERIFICATION_PENDING, False),
        (WhatsAppCloudConnectionStatus.DISABLED, False),
    ],
)
def test_connection_allows_outbound(status: WhatsAppCloudConnectionStatus, expected: bool) -> None:
    assert connection_allows_outbound(status) is expected


def test_active_connection_requires_credential_references() -> None:
    with pytest.raises(WhatsAppCloudConnectionError, match="credential"):
        vw_whatsapp_connection(
            include_credentials=False, status=WhatsAppCloudConnectionStatus.ACTIVE
        )


def test_draft_connection_allows_missing_credentials() -> None:
    connection = vw_whatsapp_connection(
        include_credentials=False,
        status=WhatsAppCloudConnectionStatus.DRAFT,
    )
    assert connection.access_token_ref is None
    assert not connection_requires_credentials(WhatsAppCloudConnectionStatus.DRAFT)


def test_connection_rejects_invalid_graph_api_version() -> None:
    with pytest.raises(ValueError, match="graph_api_version"):
        WhatsAppCloudConnection(
            id=VW_WHATSAPP_CONNECTION_ID,
            tenant_id=TENANT_A_ID,
            channel_connection_id=VW_CHANNEL_CONNECTION_ID,
            provider=ProviderKind.WHATSAPP_CLOUD,
            app_id="900100200300",
            waba_id="800100200300",
            phone_number_id="100200300400",
            display_phone_number="+15550001",
            graph_api_version="21.0",
            access_token_ref=None,
            app_secret_ref=None,
            verify_token_ref=None,
            status=WhatsAppCloudConnectionStatus.DRAFT,
            webhook_subscription_status=WebhookSubscriptionStatus.NOT_CONFIGURED,
            capabilities=frozenset({ProviderCapability.INBOUND_TEXT}),
            webhook_public_key="a1b2c3d4e5f6789012345678901234567890abcd",
            created_at=_NOW,
            updated_at=_NOW,
            last_verified_at=None,
            version=1,
        )


def test_messaging_policy_allows_free_form_inside_window() -> None:
    policy = WhatsAppMessagingPolicy()
    decision = policy.evaluate_send(
        kind=OutboundMessageKind.FREE_FORM_TEXT,
        last_customer_inbound_at=_NOW - timedelta(hours=1),
        now=_NOW,
    )
    assert decision.allowed is True
    assert decision.violation is None


def test_messaging_policy_requires_template_outside_window() -> None:
    policy = WhatsAppMessagingPolicy()
    decision = policy.evaluate_send(
        kind=OutboundMessageKind.FREE_FORM_TEXT,
        last_customer_inbound_at=_NOW - timedelta(hours=25),
        now=_NOW,
    )
    assert decision.allowed is False
    assert decision.violation is MessagingPolicyViolation.TEMPLATE_REQUIRED


def test_messaging_policy_always_allows_approved_template() -> None:
    policy = WhatsAppMessagingPolicy()
    decision = policy.evaluate_send(
        kind=OutboundMessageKind.APPROVED_TEMPLATE,
        last_customer_inbound_at=None,
        now=_NOW,
    )
    assert decision.allowed is True


def test_messaging_policy_require_allowed_raises() -> None:
    policy = WhatsAppMessagingPolicy()
    with pytest.raises(WhatsAppMessagingPolicyError, match="template_required"):
        policy.require_allowed(
            kind=OutboundMessageKind.FREE_FORM_TEXT,
            last_customer_inbound_at=None,
            now=_NOW,
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OutboundMessageStatus.DRAFT, OutboundMessageStatus.PENDING_APPROVAL),
        (OutboundMessageStatus.PENDING_APPROVAL, OutboundMessageStatus.APPROVED),
        (OutboundMessageStatus.APPROVED, OutboundMessageStatus.QUEUED),
        (OutboundMessageStatus.QUEUED, OutboundMessageStatus.SENDING),
        (OutboundMessageStatus.SENDING, OutboundMessageStatus.PROVIDER_ACCEPTED),
        (OutboundMessageStatus.SENDING, OutboundMessageStatus.DELIVERY_UNKNOWN),
    ],
)
def test_outbound_allowed_transitions(
    current: OutboundMessageStatus,
    target: OutboundMessageStatus,
) -> None:
    validate_outbound_message_transition(current=current, target=target)


def test_outbound_disallowed_transition_raises() -> None:
    with pytest.raises(OutboundMessageTransitionError):
        validate_outbound_message_transition(
            current=OutboundMessageStatus.PROVIDER_ACCEPTED,
            target=OutboundMessageStatus.QUEUED,
        )


def test_outbound_send_may_proceed_only_from_queued() -> None:
    assert outbound_send_may_proceed(OutboundMessageStatus.QUEUED) is True
    assert outbound_send_may_proceed(OutboundMessageStatus.SENDING) is False


@pytest.mark.parametrize(
    "status",
    [
        OutboundMessageStatus.PROVIDER_ACCEPTED,
        OutboundMessageStatus.DELIVERY_UNKNOWN,
        OutboundMessageStatus.DELIVERED,
        OutboundMessageStatus.READ,
    ],
)
def test_outbound_resend_prohibited(status: OutboundMessageStatus) -> None:
    assert outbound_resend_prohibited(status) is True
    message = _outbound_message(status=status)
    assert message.status is status


def test_whatsapp_connection_repr_hides_secrets() -> None:
    connection = vw_whatsapp_connection()
    rendered = repr(connection)
    assert "Secret" not in rendered
    assert VW_WHATSAPP_CONNECTION_ID.hex in rendered or str(VW_WHATSAPP_CONNECTION_ID) in rendered
    assert GRAPH_API_VERSION in connection.graph_api_version
