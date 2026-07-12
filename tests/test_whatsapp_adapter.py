"""Unit tests for Meta WhatsApp Cloud webhook adapter."""

from __future__ import annotations

import asyncio

import pytest
from closeros.application.provider_ports import ProviderPayloadError, ProviderSignatureError
from closeros.domain.canonical_enums import DeliveryStatus, MessageDirection, ParticipantSenderType
from closeros.domain.normalized_operations import (
    NormalizedDeliveryStatusChanged,
    NormalizedMessageReceived,
)
from closeros.domain.provider_credentials import SecretBytes
from closeros.infrastructure.injected_whatsapp_credential_resolver import (
    InjectedWhatsAppCredentialResolver,
)
from closeros.infrastructure.whatsapp_cloud_adapter import WhatsAppCloudWebhookAdapter

from tests.tenant_persistence_support import TENANT_A_ID
from tests.vw_support import (
    GRAPH_API_VERSION,
    VW_APP_SECRET,
    VW_APP_SECRET_REF,
    VW_CHANNEL_CONNECTION_ID,
    VW_WHATSAPP_CONNECTION_ID,
    build_whatsapp_interactive_message_payload,
    build_whatsapp_media_message_payload,
    build_whatsapp_status_payload,
    build_whatsapp_text_message_payload,
    build_whatsapp_unknown_type_payload,
    build_whatsapp_webhook_headers,
)


def _adapter(*, secret: bytes = VW_APP_SECRET) -> WhatsAppCloudWebhookAdapter:
    resolver = InjectedWhatsAppCredentialResolver(
        secrets_by_reference={VW_APP_SECRET_REF: secret},
    )

    async def resolve_app_secret_for_channel(
        tenant_id: object,
        channel_connection_id: object,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = channel_connection_id
        return await resolver.resolve_app_secret(
            tenant_id=TENANT_A_ID,
            whatsapp_connection_id=VW_WHATSAPP_CONNECTION_ID,
            reference_key=VW_APP_SECRET_REF,
        )

    return WhatsAppCloudWebhookAdapter(
        resolve_app_secret_for_channel=resolve_app_secret_for_channel,
        graph_api_version=GRAPH_API_VERSION,
    )


def test_adapter_verifies_valid_signature() -> None:
    adapter = _adapter()
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)

    async def exercise() -> None:
        result = await adapter.verify_webhook(
            raw_body=body,
            headers=headers,
            connection_id=VW_CHANNEL_CONNECTION_ID,
            tenant_id=TENANT_A_ID,
        )
        assert result.external_event_id
        assert result.raw_body == body

    asyncio.run(exercise())


def test_adapter_rejects_invalid_signature() -> None:
    adapter = _adapter()
    body = build_whatsapp_text_message_payload()
    headers = build_whatsapp_webhook_headers(body=body)
    headers["x-hub-signature-256"] = "sha256=deadbeef"

    async def exercise() -> None:
        with pytest.raises(ProviderSignatureError):
            await adapter.verify_webhook(
                raw_body=body,
                headers=headers,
                connection_id=VW_CHANNEL_CONNECTION_ID,
                tenant_id=TENANT_A_ID,
            )

    asyncio.run(exercise())


def test_adapter_rejects_missing_signature_header() -> None:
    adapter = _adapter()
    body = build_whatsapp_text_message_payload()

    async def exercise() -> None:
        with pytest.raises(ProviderSignatureError):
            await adapter.verify_webhook(
                raw_body=body,
                headers={"content-type": "application/json"},
                connection_id=VW_CHANNEL_CONNECTION_ID,
                tenant_id=TENANT_A_ID,
            )

    asyncio.run(exercise())


def test_adapter_normalizes_text_message() -> None:
    adapter = _adapter()
    body = build_whatsapp_text_message_payload(body="Pricing question")
    operations = adapter.normalize_payload(decrypted_payload=body, content_type="application/json")
    assert len(operations) == 1
    message = operations[0]
    assert isinstance(message, NormalizedMessageReceived)
    assert message.sender_type is ParticipantSenderType.CUSTOMER
    assert message.direction is MessageDirection.INBOUND
    assert message.raw_message_bytes == b"Pricing question"


def test_adapter_normalizes_interactive_reply() -> None:
    adapter = _adapter()
    body = build_whatsapp_interactive_message_payload(title="Confirm order")
    operations = adapter.normalize_payload(decrypted_payload=body, content_type="application/json")
    first = operations[0]
    assert isinstance(first, NormalizedMessageReceived)
    assert first.raw_message_bytes == b"Confirm order"


def test_adapter_normalizes_delivery_status() -> None:
    adapter = _adapter()
    body = build_whatsapp_status_payload(status="read")
    operations = adapter.normalize_payload(decrypted_payload=body, content_type="application/json")
    assert len(operations) == 1
    status_event = operations[0]
    assert isinstance(status_event, NormalizedDeliveryStatusChanged)
    assert status_event.delivery_status is DeliveryStatus.READ


def test_adapter_normalizes_media_with_quarantine_placeholder() -> None:
    adapter = _adapter()
    body = build_whatsapp_media_message_payload()
    operations = adapter.normalize_payload(decrypted_payload=body, content_type="application/json")
    media_op = operations[0]
    assert isinstance(media_op, NormalizedMessageReceived)
    assert media_op.raw_message_bytes == b"[media unavailable pending scan]"
    metadata = media_op.adapter_metadata.as_dict()
    assert metadata.get("media_reference") == "quarantined_pending_scan"
    assert metadata.get("wa_media_ref") == "media-ref-001"


def test_adapter_skips_unknown_message_types() -> None:
    adapter = _adapter()
    body = build_whatsapp_unknown_type_payload()
    operations = adapter.normalize_payload(decrypted_payload=body, content_type="application/json")
    assert operations == ()


def test_adapter_rejects_malformed_json() -> None:
    adapter = _adapter()
    with pytest.raises(ProviderPayloadError, match="malformed"):
        adapter.normalize_payload(decrypted_payload=b"{not-json", content_type="application/json")


def test_adapter_rejects_malformed_text_message() -> None:
    adapter = _adapter()
    body = build_whatsapp_text_message_payload()
    document = __import__("json").loads(body.decode("utf-8"))
    document["entry"][0]["changes"][0]["value"]["messages"][0]["text"] = {"body": ""}
    malformed = __import__("json").dumps(document).encode("utf-8")
    with pytest.raises(ProviderPayloadError, match="malformed"):
        adapter.normalize_payload(decrypted_payload=malformed, content_type="application/json")
