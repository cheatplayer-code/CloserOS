"""Official Meta WhatsApp Cloud webhook adapter.

Documentation review date: 2026-07-12
Graph API version: v21.0
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from closeros.application.provider_ports import (
    ProviderPayloadError,
    ProviderSignatureError,
    VerifiedWebhookResult,
)
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.canonical_enums import (
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
    ProviderKind,
)
from closeros.domain.normalized_operations import (
    NormalizedDeliveryStatusChanged,
    NormalizedMessageReceived,
    NormalizedOperation,
    validate_normalized_operations,
)
from closeros.domain.provider_credentials import SecretBytes

_SIGNATURE_HEADER = "x-hub-signature-256"
_MAX_ENTRIES = 10
_MAX_CHANGES = 10
_MAX_MESSAGES_PER_CHANGE = 50
_MAX_STATUSES_PER_CHANGE = 50
_MEDIA_PLACEHOLDER_TEXT = "[media unavailable pending scan]"

_ResolveAppSecretForChannel = Callable[[UUID, UUID], Awaitable[SecretBytes | None]]


def _parse_unix_timestamp(value: object) -> datetime:
    if isinstance(value, str) and value.isdigit():
        seconds = int(value)
    elif isinstance(value, int):
        seconds = value
    else:
        raise ProviderPayloadError("timestamp is malformed")
    return datetime.fromtimestamp(seconds, tz=UTC)


class WhatsAppCloudWebhookAdapter:
    def __init__(
        self,
        *,
        resolve_app_secret_for_channel: _ResolveAppSecretForChannel,
        graph_api_version: str,
    ) -> None:
        if not graph_api_version.strip():
            raise ValueError("graph_api_version must not be empty")
        self._resolve_app_secret_for_channel = resolve_app_secret_for_channel
        self._graph_api_version = graph_api_version.strip()

    @property
    def provider_kind(self) -> ProviderKind:
        return ProviderKind.WHATSAPP_CLOUD

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        connection_id: UUID,
        tenant_id: UUID,
    ) -> VerifiedWebhookResult:
        if type(raw_body) is not bytes or not raw_body:
            raise ProviderSignatureError("webhook verification failed")

        normalized_headers = {key.lower(): value for key, value in headers.items()}
        signature_header = normalized_headers.get(_SIGNATURE_HEADER)
        if not signature_header or not signature_header.startswith("sha256="):
            raise ProviderSignatureError("webhook verification failed")

        app_secret = await self._resolve_app_secret_for_channel(tenant_id, connection_id)
        if app_secret is None:
            raise ProviderSignatureError("webhook verification failed")

        provided_digest = signature_header.removeprefix("sha256=").strip()
        expected_digest = hmac.new(
            app_secret.value,
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(provided_digest, expected_digest):
            raise ProviderSignatureError("webhook verification failed")

        external_event_id = _extract_external_event_id(raw_body)
        provider_event_at = _extract_provider_event_at(raw_body)

        return VerifiedWebhookResult(
            external_event_id=external_event_id,
            received_content_type="application/json",
            adapter_metadata=AdapterMetadata.from_mapping(
                {
                    "adapter": "whatsapp_cloud",
                    "graph_api_version": self._graph_api_version,
                }
            ),
            provider_event_at=provider_event_at,
            raw_body=raw_body,
        )

    def normalize_payload(
        self,
        *,
        decrypted_payload: bytes,
        content_type: str,
    ) -> tuple[NormalizedOperation, ...]:
        _ = content_type
        try:
            document = json.loads(decrypted_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderPayloadError("provider payload is malformed") from error

        if not isinstance(document, dict):
            raise ProviderPayloadError("provider payload is malformed")

        entries = document.get("entry")
        if not isinstance(entries, list) or not entries:
            raise ProviderPayloadError("provider payload is malformed")
        if len(entries) > _MAX_ENTRIES:
            raise ProviderPayloadError("provider payload exceeds entry limit")

        operations: list[NormalizedOperation] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProviderPayloadError("provider payload is malformed")
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            if len(changes) > _MAX_CHANGES:
                raise ProviderPayloadError("provider payload exceeds change limit")
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                metadata = value.get("metadata")
                phone_number_id = None
                if isinstance(metadata, dict) and isinstance(metadata.get("phone_number_id"), str):
                    phone_number_id = metadata["phone_number_id"].strip()

                contacts = value.get("contacts")
                contact_wa_id = _extract_contact_wa_id(contacts)

                messages = value.get("messages")
                if isinstance(messages, list):
                    if len(messages) > _MAX_MESSAGES_PER_CHANGE:
                        raise ProviderPayloadError("provider payload exceeds message limit")
                    for message in messages:
                        if not isinstance(message, dict):
                            continue
                        message_operation = _normalize_inbound_message(
                            message=message,
                            contact_wa_id=contact_wa_id,
                            phone_number_id=phone_number_id,
                        )
                        if message_operation is not None:
                            operations.append(message_operation)

                statuses = value.get("statuses")
                if isinstance(statuses, list):
                    if len(statuses) > _MAX_STATUSES_PER_CHANGE:
                        raise ProviderPayloadError("provider payload exceeds status limit")
                    for status_event in statuses:
                        if not isinstance(status_event, dict):
                            continue
                        status_operation = _normalize_status_event(
                            status_event=status_event,
                            contact_wa_id=contact_wa_id,
                            phone_number_id=phone_number_id,
                        )
                        if status_operation is not None:
                            operations.append(status_operation)

        return validate_normalized_operations(tuple(operations))


def build_whatsapp_signature(*, app_secret: bytes, body: bytes) -> str:
    digest = hmac.new(app_secret, body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _extract_external_event_id(raw_body: bytes) -> str:
    try:
        document = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderSignatureError("webhook verification failed") from error
    if not isinstance(document, dict):
        raise ProviderSignatureError("webhook verification failed")
    entries = document.get("entry")
    if not isinstance(entries, list) or not entries:
        raise ProviderSignatureError("webhook verification failed")
    first_entry = entries[0]
    if not isinstance(first_entry, dict):
        raise ProviderSignatureError("webhook verification failed")
    entry_id = first_entry.get("id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise ProviderSignatureError("webhook verification failed")
    return entry_id.strip()


def _extract_provider_event_at(raw_body: bytes) -> datetime | None:
    try:
        document = json.loads(raw_body.decode("utf-8"))
        if not isinstance(document, dict):
            return None
        entries = document.get("entry")
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                messages = value.get("messages")
                if isinstance(messages, list) and messages:
                    first = messages[0]
                    if isinstance(first, dict) and "timestamp" in first:
                        return _parse_unix_timestamp(first["timestamp"])
                statuses = value.get("statuses")
                if isinstance(statuses, list) and statuses:
                    first = statuses[0]
                    if isinstance(first, dict) and "timestamp" in first:
                        return _parse_unix_timestamp(first["timestamp"])
    except (ProviderPayloadError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return None


def _extract_contact_wa_id(contacts: object) -> str | None:
    if not isinstance(contacts, list) or not contacts:
        return None
    first = contacts[0]
    if not isinstance(first, dict):
        return None
    wa_id = first.get("wa_id")
    if isinstance(wa_id, str) and wa_id.strip():
        return wa_id.strip()
    return None


def _normalize_inbound_message(
    *,
    message: dict[str, Any],
    contact_wa_id: str | None,
    phone_number_id: str | None,
) -> NormalizedMessageReceived | None:
    external_message_id = message.get("id")
    sender = message.get("from")
    timestamp = message.get("timestamp")
    message_type = message.get("type")
    if not isinstance(external_message_id, str) or not external_message_id.strip():
        return None
    if not isinstance(sender, str) or not sender.strip():
        return None

    external_conversation_id = sender.strip()
    occurred_at = _parse_unix_timestamp(timestamp)
    adapter_metadata = AdapterMetadata.from_mapping(
        {
            "provider": "whatsapp_cloud",
            "inbound_kind": str(message_type) if message_type is not None else "unknown",
        }
    )

    if message_type == "text":
        text = message.get("text")
        if not isinstance(text, dict):
            raise ProviderPayloadError("text message is malformed")
        body = text.get("body")
        if not isinstance(body, str) or not body:
            raise ProviderPayloadError("text message is malformed")
        raw_bytes = body.encode("utf-8")
    elif message_type == "interactive":
        interactive = message.get("interactive")
        if not isinstance(interactive, dict):
            raise ProviderPayloadError("interactive message is malformed")
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if not isinstance(reply, dict):
            raise ProviderPayloadError("interactive message is malformed")
        title = reply.get("title")
        if not isinstance(title, str) or not title:
            raise ProviderPayloadError("interactive message is malformed")
        raw_bytes = title.encode("utf-8")
    elif message_type == "reaction":
        reaction = message.get("reaction")
        if not isinstance(reaction, dict):
            raise ProviderPayloadError("reaction message is malformed")
        emoji = reaction.get("emoji")
        if not isinstance(emoji, str) or not emoji:
            raise ProviderPayloadError("reaction message is malformed")
        raw_bytes = emoji.encode("utf-8")
    elif message_type in {"image", "audio", "video", "document", "sticker"}:
        media_object = message.get(message_type)
        media_id = None
        mime_type = None
        if isinstance(media_object, dict):
            if isinstance(media_object.get("id"), str):
                media_id = media_object["id"].strip()
            if isinstance(media_object.get("mime_type"), str):
                mime_type = media_object["mime_type"].strip()
        adapter_metadata = AdapterMetadata.from_mapping(
            {
                **adapter_metadata.as_dict(),
                "media_reference": "quarantined_pending_scan",
                **({"wa_media_ref": media_id} if media_id else {}),
                **({"mime_type": mime_type} if mime_type else {}),
            }
        )
        raw_bytes = _MEDIA_PLACEHOLDER_TEXT.encode("utf-8")
    else:
        return None

    return NormalizedMessageReceived(
        external_conversation_id=external_conversation_id,
        external_message_id=external_message_id.strip(),
        sender_type=ParticipantSenderType.CUSTOMER,
        direction=MessageDirection.INBOUND,
        sent_at=occurred_at,
        received_at=occurred_at,
        reply_to_external_message_id=None,
        adapter_metadata=adapter_metadata,
        raw_message_bytes=raw_bytes,
    )


def _normalize_status_event(
    *,
    status_event: dict[str, Any],
    contact_wa_id: str | None,
    phone_number_id: str | None,
) -> NormalizedDeliveryStatusChanged | None:
    external_message_id = status_event.get("id")
    status_value = status_event.get("status")
    timestamp = status_event.get("timestamp")
    recipient_id = status_event.get("recipient_id")
    external_event_id = status_event.get("id")
    if not isinstance(external_message_id, str) or not external_message_id.strip():
        return None
    if not isinstance(status_value, str):
        return None

    delivery_status = _map_delivery_status(status_value)
    if delivery_status is None:
        return None

    external_conversation_id = (
        recipient_id.strip()
        if isinstance(recipient_id, str) and recipient_id.strip()
        else (contact_wa_id or "unknown")
    )
    occurred_at = _parse_unix_timestamp(timestamp)

    return NormalizedDeliveryStatusChanged(
        external_conversation_id=external_conversation_id,
        external_message_id=external_message_id.strip(),
        external_event_id=(
            external_event_id.strip()
            if isinstance(external_event_id, str) and external_event_id.strip()
            else external_message_id.strip()
        ),
        delivery_status=delivery_status,
        occurred_at=occurred_at,
        adapter_metadata=AdapterMetadata.from_mapping(
            {
                "provider": "whatsapp_cloud",
                "delivery_kind": status_value,
            }
        ),
    )


def _map_delivery_status(value: str) -> DeliveryStatus | None:
    normalized = value.strip().lower()
    if normalized == "sent":
        return DeliveryStatus.SENT
    if normalized == "delivered":
        return DeliveryStatus.DELIVERED
    if normalized == "read":
        return DeliveryStatus.READ
    if normalized == "failed":
        return DeliveryStatus.FAILED
    return None
