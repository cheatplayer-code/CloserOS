"""Development/test-only synthetic HMAC webhook adapter.

NOT FOR PRODUCTION. Uses stdlib HMAC-SHA-256 with injected secret material.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import datetime
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
    NormalizedMessageDeleted,
    NormalizedMessageEdited,
    NormalizedMessageReceived,
    NormalizedOperation,
    validate_normalized_operations,
)

_SIGNATURE_HEADER = "x-synthetic-signature"
_EVENT_ID_HEADER = "x-synthetic-event-id"
_CONTENT_TYPE_HEADER = "content-type"


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProviderPayloadError(f"{field_name} must be timezone-aware")
    return parsed


class SyntheticHmacWebhookAdapter:
    """Non-production adapter for integration tests and local development."""

    def __init__(self, *, secret: bytes) -> None:
        if type(secret) is not bytes or not secret:
            raise ValueError("secret must be non-empty bytes")
        self._secret = secret

    @property
    def provider_kind(self) -> ProviderKind:
        return ProviderKind.SYNTHETIC

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        connection_id: UUID,
        tenant_id: UUID,
    ) -> VerifiedWebhookResult:
        _ = connection_id
        _ = tenant_id

        if type(raw_body) is not bytes or not raw_body:
            raise ProviderSignatureError("webhook verification failed")

        normalized_headers = {key.lower(): value for key, value in headers.items()}
        signature = normalized_headers.get(_SIGNATURE_HEADER)
        if not signature:
            raise ProviderSignatureError("webhook verification failed")

        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.strip(), expected):
            raise ProviderSignatureError("webhook verification failed")

        external_event_id = normalized_headers.get(_EVENT_ID_HEADER)
        if not external_event_id or not external_event_id.strip():
            raise ProviderSignatureError("webhook verification failed")

        content_type = normalized_headers.get(_CONTENT_TYPE_HEADER, "application/json")

        provider_event_at: datetime | None = None
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("event_at"), str):
                provider_event_at = _parse_iso_datetime(payload["event_at"], "event_at")
        except (UnicodeDecodeError, json.JSONDecodeError, ProviderPayloadError):
            provider_event_at = None

        return VerifiedWebhookResult(
            external_event_id=external_event_id.strip(),
            received_content_type=content_type.strip(),
            adapter_metadata=AdapterMetadata.from_mapping({"adapter": "synthetic"}),
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

        raw_operations = document.get("operations")
        if not isinstance(raw_operations, list):
            raise ProviderPayloadError("provider payload is malformed")

        normalized: list[NormalizedOperation] = []

        for raw_operation in raw_operations:
            if not isinstance(raw_operation, dict):
                raise ProviderPayloadError("provider payload is malformed")

            kind = raw_operation.get("kind")
            metadata = AdapterMetadata.from_mapping(raw_operation.get("metadata"))

            if kind == "message_received":
                normalized.append(
                    NormalizedMessageReceived(
                        external_conversation_id=raw_operation["external_conversation_id"],
                        external_message_id=raw_operation["external_message_id"],
                        sender_type=ParticipantSenderType(raw_operation["sender_type"]),
                        direction=MessageDirection(raw_operation["direction"]),
                        sent_at=_parse_iso_datetime(raw_operation["sent_at"], "sent_at"),
                        received_at=_parse_iso_datetime(
                            raw_operation["received_at"], "received_at"
                        ),
                        reply_to_external_message_id=raw_operation.get(
                            "reply_to_external_message_id"
                        ),
                        adapter_metadata=metadata,
                        raw_message_bytes=raw_operation["message_text"].encode("utf-8"),
                    )
                )
            elif kind == "message_edited":
                normalized.append(
                    NormalizedMessageEdited(
                        external_conversation_id=raw_operation["external_conversation_id"],
                        external_message_id=raw_operation["external_message_id"],
                        external_event_id=raw_operation["external_event_id"],
                        occurred_at=_parse_iso_datetime(
                            raw_operation["occurred_at"], "occurred_at"
                        ),
                        adapter_metadata=metadata,
                        replacement_bytes=raw_operation["message_text"].encode("utf-8"),
                    )
                )
            elif kind == "message_deleted":
                normalized.append(
                    NormalizedMessageDeleted(
                        external_conversation_id=raw_operation["external_conversation_id"],
                        external_message_id=raw_operation["external_message_id"],
                        external_event_id=raw_operation["external_event_id"],
                        occurred_at=_parse_iso_datetime(
                            raw_operation["occurred_at"], "occurred_at"
                        ),
                        adapter_metadata=metadata,
                    )
                )
            elif kind == "delivery_status_changed":
                normalized.append(
                    NormalizedDeliveryStatusChanged(
                        external_conversation_id=raw_operation["external_conversation_id"],
                        external_message_id=raw_operation["external_message_id"],
                        external_event_id=raw_operation["external_event_id"],
                        delivery_status=DeliveryStatus(raw_operation["delivery_status"]),
                        occurred_at=_parse_iso_datetime(
                            raw_operation["occurred_at"], "occurred_at"
                        ),
                        adapter_metadata=metadata,
                    )
                )
            else:
                raise ProviderPayloadError("unsupported provider operation")

        return validate_normalized_operations(tuple(normalized))


def build_synthetic_signature(*, secret: bytes, body: bytes) -> str:
    """Test helper for computing synthetic adapter signatures."""
    return hmac.new(secret, body, hashlib.sha256).hexdigest()
