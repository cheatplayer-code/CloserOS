"""WhatsApp Cloud (Block VW) test helpers and fabricated Meta webhook payloads."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from closeros.domain.canonical_enums import ChannelConnectionStatus, ProviderKind
from closeros.domain.channel_connection import ChannelConnection
from closeros.domain.provider_capability import ProviderCapability
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnection,
    WhatsAppCloudConnectionStatus,
)
from closeros.infrastructure.whatsapp_cloud_adapter import build_whatsapp_signature

from tests.canonical_persistence_support import NOW, synthetic_adapter_metadata
from tests.tenant_persistence_support import TENANT_A_ID

GRAPH_API_VERSION = "v21.0"
WABA_ENTRY_ID = "123456789012345"
PHONE_NUMBER_ID = "100200300400"
CUSTOMER_WA_ID = "15551234567"

VW_CHANNEL_CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000161")
VW_WHATSAPP_CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000160")
VW_WEBHOOK_PUBLIC_KEY = "a1b2c3d4e5f6789012345678901234567890abcd"

VW_ACCESS_TOKEN_REF = "VW_TEST_ACCESS_TOKEN"
VW_APP_SECRET_REF = "VW_TEST_APP_SECRET"
VW_VERIFY_TOKEN_REF = "VW_TEST_VERIFY_TOKEN"

VW_THREAD_ID = UUID("00000000-0000-0000-0000-000000000162")
VW_OUTBOUND_MESSAGE_ID = UUID("00000000-0000-0000-0000-000000000163")
VW_OUTBOUND_CONTENT_ID = UUID("00000000-0000-0000-0000-000000000164")
VW_USER_ID = UUID("00000000-0000-0000-0000-000000000010")


def build_runtime_secret(*parts: str) -> bytes:
    """Construct deterministic non-production secrets from short runtime components."""
    return "".join(parts).encode("utf-8")


VW_APP_SECRET = build_runtime_secret("vw", "-", "app", "-", "secret", "-", "32bytes!!")
VW_ACCESS_TOKEN = build_runtime_secret("vw", "-", "access", "-", "token", "-", "value!!")
VW_VERIFY_TOKEN = build_runtime_secret("vw", "-", "verify", "-", "token", "-", "ok!!")


def vw_credential_environ() -> dict[str, str]:
    return {
        VW_ACCESS_TOKEN_REF: VW_ACCESS_TOKEN.decode("utf-8"),
        VW_APP_SECRET_REF: VW_APP_SECRET.decode("utf-8"),
        VW_VERIFY_TOKEN_REF: VW_VERIFY_TOKEN.decode("utf-8"),
    }


def vw_channel_connection(
    *,
    connection_id: UUID = VW_CHANNEL_CONNECTION_ID,
    tenant_id: UUID = TENANT_A_ID,
    status: ChannelConnectionStatus = ChannelConnectionStatus.ACTIVE,
) -> ChannelConnection:
    return ChannelConnection(
        id=connection_id,
        tenant_id=tenant_id,
        provider=ProviderKind.WHATSAPP_CLOUD,
        external_connection_id=PHONE_NUMBER_ID,
        status=status,
        adapter_metadata=synthetic_adapter_metadata(provider="whatsapp_cloud"),
        created_at=NOW,
        updated_at=NOW,
    )


def vw_whatsapp_connection(
    *,
    connection_id: UUID = VW_WHATSAPP_CONNECTION_ID,
    channel_connection_id: UUID = VW_CHANNEL_CONNECTION_ID,
    tenant_id: UUID = TENANT_A_ID,
    status: WhatsAppCloudConnectionStatus = WhatsAppCloudConnectionStatus.ACTIVE,
    webhook_public_key: str = VW_WEBHOOK_PUBLIC_KEY,
    include_credentials: bool = True,
) -> WhatsAppCloudConnection:
    return WhatsAppCloudConnection(
        id=connection_id,
        tenant_id=tenant_id,
        channel_connection_id=channel_connection_id,
        provider=ProviderKind.WHATSAPP_CLOUD,
        app_id="900100200300",
        waba_id="800100200300",
        phone_number_id=PHONE_NUMBER_ID,
        display_phone_number="+15550001",
        graph_api_version=GRAPH_API_VERSION,
        access_token_ref=VW_ACCESS_TOKEN_REF if include_credentials else None,
        app_secret_ref=VW_APP_SECRET_REF if include_credentials else None,
        verify_token_ref=VW_VERIFY_TOKEN_REF if include_credentials else None,
        status=status,
        webhook_subscription_status=WebhookSubscriptionStatus.SUBSCRIBED,
        capabilities=frozenset(
            {
                ProviderCapability.INBOUND_TEXT,
                ProviderCapability.INTERACTIVE_REPLY,
                ProviderCapability.REACTION,
                ProviderCapability.MESSAGE_STATUS,
                ProviderCapability.MEDIA_REFERENCE,
                ProviderCapability.OUTBOUND_FREE_FORM_TEXT,
                ProviderCapability.OUTBOUND_APPROVED_TEMPLATE,
            }
        ),
        webhook_public_key=webhook_public_key,
        created_at=NOW,
        updated_at=NOW,
        last_verified_at=NOW,
        version=1,
    )


def _base_change_value(
    *, messages: list[dict[str, Any]] | None = None, statuses: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "+15550001",
            "phone_number_id": PHONE_NUMBER_ID,
        },
        "contacts": [
            {
                "profile": {"name": "Synthetic Customer"},
                "wa_id": CUSTOMER_WA_ID,
            }
        ],
    }
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return value


def _wrap_payload(*, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ENTRY_ID,
                "changes": [
                    {
                        "value": value,
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def build_whatsapp_text_message_payload(
    *,
    body: str = "Synthetic inbound WhatsApp text",
    external_message_id: str = "wamid.vw.text001",
    timestamp: int | str = 1718186400,
) -> bytes:
    payload = _wrap_payload(
        value=_base_change_value(
            messages=[
                {
                    "from": CUSTOMER_WA_ID,
                    "id": external_message_id,
                    "timestamp": str(timestamp),
                    "type": "text",
                    "text": {"body": body},
                }
            ]
        )
    )
    return json.dumps(payload).encode("utf-8")


def build_whatsapp_interactive_message_payload(
    *,
    title: str = "Yes, continue",
    external_message_id: str = "wamid.vw.interactive001",
) -> bytes:
    payload = _wrap_payload(
        value=_base_change_value(
            messages=[
                {
                    "from": CUSTOMER_WA_ID,
                    "id": external_message_id,
                    "timestamp": "1718186401",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "btn-1", "title": title},
                    },
                }
            ]
        )
    )
    return json.dumps(payload).encode("utf-8")


def build_whatsapp_status_payload(
    *,
    status: str = "delivered",
    external_message_id: str = "wamid.vw.status001",
) -> bytes:
    payload = _wrap_payload(
        value=_base_change_value(
            statuses=[
                {
                    "id": external_message_id,
                    "status": status,
                    "timestamp": "1718186402",
                    "recipient_id": CUSTOMER_WA_ID,
                }
            ]
        )
    )
    return json.dumps(payload).encode("utf-8")


def build_whatsapp_media_message_payload(
    *,
    media_type: str = "image",
    media_id: str = "media-ref-001",
    mime_type: str = "image/jpeg",
    external_message_id: str = "wamid.vw.media001",
) -> bytes:
    payload = _wrap_payload(
        value=_base_change_value(
            messages=[
                {
                    "from": CUSTOMER_WA_ID,
                    "id": external_message_id,
                    "timestamp": "1718186403",
                    "type": media_type,
                    media_type: {"id": media_id, "mime_type": mime_type},
                }
            ]
        )
    )
    return json.dumps(payload).encode("utf-8")


def build_whatsapp_unknown_type_payload() -> bytes:
    payload = _wrap_payload(
        value=_base_change_value(
            messages=[
                {
                    "from": CUSTOMER_WA_ID,
                    "id": "wamid.vw.unknown001",
                    "timestamp": "1718186404",
                    "type": "unsupported_future_type",
                    "future_field": {"nested": True},
                }
            ]
        )
    )
    return json.dumps(payload).encode("utf-8")


def build_whatsapp_webhook_headers(
    *,
    body: bytes,
    app_secret: bytes = VW_APP_SECRET,
) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "x-hub-signature-256": build_whatsapp_signature(app_secret=app_secret, body=body),
    }


def whatsapp_hub_verify_query(
    *, verify_token: str = VW_VERIFY_TOKEN.decode("utf-8")
) -> dict[str, str]:
    return {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": "challenge-token-12345",
    }


def recent_customer_inbound_at(*, hours_ago: float = 1.0) -> datetime:
    return datetime(2026, 7, 12, 11, 0, 0, tzinfo=UTC) - timedelta(hours=hours_ago)


def stale_customer_inbound_at() -> datetime:
    return datetime(2026, 7, 10, 11, 0, 0, tzinfo=UTC)
