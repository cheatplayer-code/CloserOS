"""Synthetic webhook and CSV ingestion test helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.channel_connection import ChannelConnection
from closeros.infrastructure.synthetic_hmac_adapter import build_synthetic_signature

from tests.canonical_persistence_support import NOW, synthetic_adapter_metadata
from tests.tenant_persistence_support import TENANT_A_ID

SYNTHETIC_WEBHOOK_SECRET = bytes(range(32))
SYNTHETIC_CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000150")
SYNTHETIC_EXTERNAL_EVENT_ID = "synthetic-event-001"


def synthetic_webhook_connection(
    *,
    connection_id: UUID = SYNTHETIC_CONNECTION_ID,
    tenant_id: UUID = TENANT_A_ID,
) -> ChannelConnection:
    from closeros.domain.canonical_enums import ChannelConnectionStatus

    return ChannelConnection(
        id=connection_id,
        tenant_id=tenant_id,
        provider=ProviderKind.SYNTHETIC,
        external_connection_id="synthetic-conn-001",
        status=ChannelConnectionStatus.ACTIVE,
        adapter_metadata=synthetic_adapter_metadata(provider="synthetic"),
        created_at=NOW,
        updated_at=NOW,
    )


def build_synthetic_message_received_payload(
    *,
    external_conversation_id: str = "conv-synthetic-001",
    external_message_id: str = "msg-synthetic-001",
    message_text: str = "Synthetic inbound message",
) -> bytes:
    payload = {
        "operations": [
            {
                "kind": "message_received",
                "external_conversation_id": external_conversation_id,
                "external_message_id": external_message_id,
                "sender_type": "customer",
                "direction": "inbound",
                "sent_at": datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC).isoformat(),
                "received_at": datetime(2026, 7, 12, 12, 0, 1, tzinfo=UTC).isoformat(),
                "message_text": message_text,
                "metadata": {"source": "synthetic"},
            }
        ]
    }
    return json.dumps(payload).encode("utf-8")


def build_synthetic_webhook_headers(
    *,
    body: bytes,
    secret: bytes = SYNTHETIC_WEBHOOK_SECRET,
    external_event_id: str = SYNTHETIC_EXTERNAL_EVENT_ID,
) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "x-synthetic-signature": build_synthetic_signature(secret=secret, body=body),
        "x-synthetic-event-id": external_event_id,
    }


def sample_csv_bytes() -> bytes:
    return (
        b"external_conversation_id,external_message_id,sender_type,direction,"
        b"sent_at,received_at,message_text\n"
        b"conv-csv-001,msg-csv-001,customer,inbound,"
        b"2026-07-12T12:00:00+00:00,2026-07-12T12:00:01+00:00,Hello from CSV\n"
    )


def default_csv_mapping() -> dict[str, int]:
    return {
        "external_conversation_id": 0,
        "external_message_id": 1,
        "sender_type": 2,
        "direction": 3,
        "sent_at": 4,
        "received_at": 5,
        "message_text": 6,
    }
