"""Integration tests for provider outbound message send outbox handler."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from closeros.application.provider_message_send_handler import (
    ProviderMessageSendHandler,
    ProviderMessageSendHandlerError,
)
from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.outbound_message import (
    OutboundMessage,
    OutboundMessageKind,
    OutboundMessageStatus,
)
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job
from closeros.domain.whatsapp_messaging_policy import WhatsAppMessagingPolicy
from closeros.infrastructure.injected_whatsapp_credential_resolver import (
    InjectedWhatsAppCredentialResolver,
)
from closeros.infrastructure.whatsapp_cloud_api_client import build_client_for_connection

from tests.auth_api_support import NOW
from tests.auth_persistence_support import USER_ID
from tests.canonical_persistence_support import (
    CONTENT_A_ID,
    MESSAGE_A_ID,
    synthetic_adapter_metadata,
    synthetic_message,
)
from tests.encryption_support import SERVICE_ID, build_content_encryption_service
from tests.tenant_persistence_support import TENANT_A_ID, synthetic_tenant
from tests.vw_support import (
    CUSTOMER_WA_ID,
    VW_ACCESS_TOKEN,
    VW_ACCESS_TOKEN_REF,
    VW_APP_SECRET,
    VW_APP_SECRET_REF,
    VW_CHANNEL_CONNECTION_ID,
    VW_OUTBOUND_CONTENT_ID,
    VW_OUTBOUND_MESSAGE_ID,
    VW_THREAD_ID,
    VW_VERIFY_TOKEN,
    VW_VERIFY_TOKEN_REF,
    recent_customer_inbound_at,
    vw_channel_connection,
    vw_whatsapp_connection,
)

pytestmark = pytest.mark.vw_persistence


def _credential_resolver() -> InjectedWhatsAppCredentialResolver:
    return InjectedWhatsAppCredentialResolver(
        secrets_by_reference={
            VW_ACCESS_TOKEN_REF: VW_ACCESS_TOKEN,
            VW_APP_SECRET_REF: VW_APP_SECRET,
            VW_VERIFY_TOKEN_REF: VW_VERIFY_TOKEN,
        },
    )


def _send_job(*, message_id: object = VW_OUTBOUND_MESSAGE_ID) -> object:
    job = build_outbox_job(
        job_id=uuid4(),
        tenant_id=TENANT_A_ID,
        job_kind=OutboxJobKind.PROVIDER_MESSAGE_SEND,
        reference=OutboxJobReference(
            tenant_id=TENANT_A_ID,
            resource_type="outbound_message",
            resource_id=message_id,  # type: ignore[arg-type]
            schema_version=1,
        ),
        deduplication_key=f"provider_message_send_{message_id}",
        created_at=NOW,
    )
    return replace(job, processing_started_at=NOW)


async def _seed_outbound_graph(
    integrated_uow_factory: Any,
    *,
    status: OutboundMessageStatus = OutboundMessageStatus.QUEUED,
    provider_message_id: str | None = None,
) -> None:
    from closeros.infrastructure import outbound_mappers as outbound_mappers
    from closeros.infrastructure import whatsapp_mappers as whatsapp_mappers

    content_encryption = build_content_encryption_service(integrated_uow_factory)
    uow = integrated_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.channel_connections.add(vw_channel_connection())
        await uow.whatsapp_cloud_connections.add(
            record=whatsapp_mappers.domain_to_record(vw_whatsapp_connection()),
        )
        await uow.conversation_threads.add(
            ConversationThread(
                id=VW_THREAD_ID,
                tenant_id=TENANT_A_ID,
                channel_connection_id=VW_CHANNEL_CONNECTION_ID,
                external_conversation_id=CUSTOMER_WA_ID,
                sales_case_id=None,
                lifecycle_status=None,
                adapter_metadata=synthetic_adapter_metadata(provider="whatsapp_cloud"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await content_encryption.encrypt_and_persist(
            uow,
            content_id=VW_OUTBOUND_CONTENT_ID,
            tenant_id=TENANT_A_ID,
            kind=EncryptedContentKind.OUTBOUND_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=b"Approved outbound body",
            created_at=NOW,
        )
        await content_encryption.encrypt_and_persist(
            uow,
            content_id=CONTENT_A_ID,
            tenant_id=TENANT_A_ID,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=b"Recent inbound for policy window",
            created_at=NOW,
        )
        await uow.messages.append(
            synthetic_message(
                message_id=MESSAGE_A_ID,
                conversation_thread_id=VW_THREAD_ID,
                content_id=CONTENT_A_ID,
                direction=MessageDirection.INBOUND,
                sender_type=ParticipantSenderType.CUSTOMER,
                received_at=recent_customer_inbound_at(),
            )
        )
        outbound = OutboundMessage(
            id=VW_OUTBOUND_MESSAGE_ID,
            tenant_id=TENANT_A_ID,
            conversation_thread_id=VW_THREAD_ID,
            channel_connection_id=VW_CHANNEL_CONNECTION_ID,
            kind=OutboundMessageKind.FREE_FORM_TEXT,
            status=status,
            encrypted_content_id=VW_OUTBOUND_CONTENT_ID,
            provider_template_id=None,
            created_by_user_id=USER_ID,
            approved_by_user_id=USER_ID,
            provider_message_id=provider_message_id,
            failure_code=None,
            created_at=NOW,
            approved_at=NOW,
            queued_at=NOW,
            sent_at=NOW if status is not OutboundMessageStatus.QUEUED else None,
            completed_at=NOW if status is OutboundMessageStatus.PROVIDER_ACCEPTED else None,
            updated_at=NOW,
            version=1,
        )
        await uow.outbound_messages.add(record=outbound_mappers.outbound_domain_to_record(outbound))
        await uow.commit()


def test_provider_message_send_handler_accepts_success(
    integrated_uow_factory: Any,
) -> None:
    request_count = {"value": 0}

    def transport(request: httpx.Request) -> httpx.Response:
        request_count["value"] += 1
        return httpx.Response(
            200,
            json={"messages": [{"id": "wamid.provider.accepted001"}]},
        )

    def client_factory(**kwargs: object) -> object:
        return build_client_for_connection(
            graph_api_version=vw_whatsapp_connection().graph_api_version,
            phone_number_id=vw_whatsapp_connection().phone_number_id,
            access_token=VW_ACCESS_TOKEN.decode("utf-8"),
            transport=httpx.MockTransport(transport),
        )

    async def exercise() -> OutboundMessageStatus:
        await _seed_outbound_graph(integrated_uow_factory)
        handler = ProviderMessageSendHandler(
            uow_factory=integrated_uow_factory,
            content_encryption=build_content_encryption_service(integrated_uow_factory),
            credential_resolver=_credential_resolver(),
            messaging_policy=WhatsAppMessagingPolicy(),
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        with patch(
            "closeros.application.provider_message_send_handler.build_client_for_connection",
            side_effect=client_factory,
        ):
            await handler.handle(job=_send_job())
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.outbound_messages.get_by_id(
                tenant_id=TENANT_A_ID,
                message_id=VW_OUTBOUND_MESSAGE_ID,
            )
        assert record is not None
        return record.status

    status = asyncio.run(exercise())
    assert status is OutboundMessageStatus.PROVIDER_ACCEPTED


def test_provider_message_send_handler_marks_delivery_unknown(
    integrated_uow_factory: Any,
) -> None:
    def transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    def client_factory(**kwargs: object) -> object:
        return build_client_for_connection(
            graph_api_version=vw_whatsapp_connection().graph_api_version,
            phone_number_id=vw_whatsapp_connection().phone_number_id,
            access_token=VW_ACCESS_TOKEN.decode("utf-8"),
            transport=httpx.MockTransport(transport),
        )

    async def exercise() -> OutboundMessageStatus:
        await _seed_outbound_graph(integrated_uow_factory)
        handler = ProviderMessageSendHandler(
            uow_factory=integrated_uow_factory,
            content_encryption=build_content_encryption_service(integrated_uow_factory),
            credential_resolver=_credential_resolver(),
            messaging_policy=WhatsAppMessagingPolicy(),
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        with (
            patch(
                "closeros.application.provider_message_send_handler.build_client_for_connection",
                side_effect=client_factory,
            ),
            pytest.raises(ProviderMessageSendHandlerError),
        ):
            await handler.handle(job=_send_job())
        uow = integrated_uow_factory()
        async with uow:
            record = await uow.outbound_messages.get_by_id(
                tenant_id=TENANT_A_ID,
                message_id=VW_OUTBOUND_MESSAGE_ID,
            )
        assert record is not None
        return record.status

    status = asyncio.run(exercise())
    assert status is OutboundMessageStatus.DELIVERY_UNKNOWN


def test_provider_message_send_handler_does_not_blind_resend(
    integrated_uow_factory: Any,
) -> None:
    request_count = {"value": 0}

    def transport(_request: httpx.Request) -> httpx.Response:
        request_count["value"] += 1
        return httpx.Response(200, json={"messages": [{"id": "wamid.resend001"}]})

    def client_factory(**kwargs: object) -> object:
        return build_client_for_connection(
            graph_api_version=vw_whatsapp_connection().graph_api_version,
            phone_number_id=vw_whatsapp_connection().phone_number_id,
            access_token=VW_ACCESS_TOKEN.decode("utf-8"),
            transport=httpx.MockTransport(transport),
        )

    async def exercise() -> None:
        await _seed_outbound_graph(
            integrated_uow_factory,
            status=OutboundMessageStatus.PROVIDER_ACCEPTED,
            provider_message_id="wamid.already-sent",
        )
        handler = ProviderMessageSendHandler(
            uow_factory=integrated_uow_factory,
            content_encryption=build_content_encryption_service(integrated_uow_factory),
            credential_resolver=_credential_resolver(),
            messaging_policy=WhatsAppMessagingPolicy(),
            service_actor_id=SERVICE_ID,
            uuid_factory=uuid4,
        )
        with patch(
            "closeros.application.provider_message_send_handler.build_client_for_connection",
            side_effect=client_factory,
        ):
            await handler.handle(job=_send_job())
        assert request_count["value"] == 0

    asyncio.run(exercise())
