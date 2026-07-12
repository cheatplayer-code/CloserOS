"""Outbox handler for provider outbound message send jobs."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbound_persistence import OutboundDeliveryAttemptRecord
from closeros.application.provider_ports import WhatsAppCredentialResolver
from closeros.application.whatsapp_audit import (
    outbound_delivery_failed_event,
    outbound_delivery_unknown_event,
    outbound_provider_accepted_event,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import (
    DeliveryStatus,
    MessageDirection,
    ParticipantSenderType,
)
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    DecryptedContent,
)
from closeros.domain.message import Message
from closeros.domain.message_events import MessageDeliveryStatusEvent
from closeros.domain.outbound_message import (
    OutboundMessage,
    OutboundMessageKind,
    OutboundMessageStatus,
    outbound_resend_prohibited,
    outbound_send_may_proceed,
    validate_outbound_message_transition,
)
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.domain.whatsapp_cloud_connection import (
    WhatsAppCloudConnection,
    connection_allows_outbound,
)
from closeros.domain.whatsapp_messaging_policy import WhatsAppMessagingPolicy
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure import whatsapp_mappers as whatsapp_mappers
from closeros.infrastructure.whatsapp_cloud_api_client import (
    WhatsAppCloudApiClientError,
    WhatsAppCloudApiResponseError,
    WhatsAppSendResult,
    WhatsAppSendTemplateRequest,
    WhatsAppSendTextRequest,
    build_client_for_connection,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class ProviderMessageSendHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("provider message send failed")


@dataclass(frozen=True, slots=True)
class ProviderMessageSendHandler:
    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    credential_resolver: WhatsAppCredentialResolver
    messaging_policy: WhatsAppMessagingPolicy
    service_actor_id: UUID
    uuid_factory: _UuidFactory

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise ProviderMessageSendHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )

        tenant_id = job.tenant_id
        outbound_message_id = job.reference.resource_id
        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)

        uow = self.uow_factory()
        async with uow:
            record = await uow.outbound_messages.get_by_id_for_update(
                tenant_id=tenant_id,
                message_id=outbound_message_id,
            )
            if record is None:
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            message = mappers.outbound_record_to_domain(record)
            if outbound_resend_prohibited(message.status):
                return
            if not outbound_send_may_proceed(message.status):
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=True,
                )
            if message.approved_by_user_id is None:
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=True,
                )

            whatsapp_records = await uow.whatsapp_cloud_connections.list_by_tenant(
                tenant_id=tenant_id
            )
            whatsapp_connection = next(
                (
                    whatsapp_mappers.record_to_domain(item)
                    for item in whatsapp_records
                    if item.channel_connection_id == message.channel_connection_id
                ),
                None,
            )
            if whatsapp_connection is None or not connection_allows_outbound(
                whatsapp_connection.status
            ):
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )

            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=message.conversation_thread_id,
            )
            if thread is None:
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )

            last_customer_inbound = await self._last_customer_inbound_at(
                uow=uow,
                tenant_id=tenant_id,
                conversation_thread_id=message.conversation_thread_id,
            )
            try:
                self.messaging_policy.require_allowed(
                    kind=message.kind,
                    last_customer_inbound_at=last_customer_inbound,
                    now=occurred_at,
                )
            except Exception as error:
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
                    permanent=True,
                ) from error

            sending = replace(
                message,
                status=OutboundMessageStatus.SENDING,
                sent_at=occurred_at,
                updated_at=occurred_at,
                version=message.version + 1,
            )
            validate_outbound_message_transition(current=message.status, target=sending.status)
            await uow.outbound_messages.update(
                record=mappers.outbound_domain_to_record(sending),
                expected_version=record.version,
            )
            await uow.commit()

        send_result, send_error = await self._call_provider(
            tenant_id=tenant_id,
            whatsapp_connection=whatsapp_connection,
            message=message,
            recipient_wa_id=thread.external_conversation_id,
            occurred_at=occurred_at,
            audit_context=audit_context,
        )

        uow = self.uow_factory()
        async with uow:
            current = await uow.outbound_messages.get_by_id_for_update(
                tenant_id=tenant_id,
                message_id=outbound_message_id,
            )
            if current is None:
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=False,
                )
            domain = mappers.outbound_record_to_domain(current)

            if send_error == "delivery_unknown":
                updated = replace(
                    domain,
                    status=OutboundMessageStatus.DELIVERY_UNKNOWN,
                    updated_at=occurred_at,
                    version=domain.version + 1,
                )
                validate_outbound_message_transition(
                    current=domain.status,
                    target=updated.status,
                )
                await self._persist_attempt(
                    uow=uow,
                    tenant_id=tenant_id,
                    outbound_message_id=outbound_message_id,
                    attempt_number=current.version,
                    started_at=occurred_at,
                    finished_at=occurred_at,
                    outcome="delivery_unknown",
                    error_code="provider_timeout",
                )
                await uow.outbound_messages.update(
                    record=mappers.outbound_domain_to_record(updated),
                    expected_version=current.version,
                )
                await append_required_audit_event(
                    uow.audit_events,
                    outbound_delivery_unknown_event(
                        tenant_id=tenant_id,
                        outbound_message_id=outbound_message_id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.commit()
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=True,
                )

            if send_result is None:
                updated = replace(
                    domain,
                    status=OutboundMessageStatus.FAILED,
                    failure_code=send_error or "provider_failed",
                    completed_at=occurred_at,
                    updated_at=occurred_at,
                    version=domain.version + 1,
                )
                validate_outbound_message_transition(
                    current=domain.status,
                    target=updated.status,
                )
                await self._persist_attempt(
                    uow=uow,
                    tenant_id=tenant_id,
                    outbound_message_id=outbound_message_id,
                    attempt_number=current.version,
                    started_at=occurred_at,
                    finished_at=occurred_at,
                    outcome="failed",
                    error_code=updated.failure_code,
                )
                await uow.outbound_messages.update(
                    record=mappers.outbound_domain_to_record(updated),
                    expected_version=current.version,
                )
                await append_required_audit_event(
                    uow.audit_events,
                    outbound_delivery_failed_event(
                        tenant_id=tenant_id,
                        outbound_message_id=outbound_message_id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                        reason_code=updated.failure_code or "provider_failed",
                    ),
                )
                await uow.commit()
                raise ProviderMessageSendHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=True,
                )

            canonical_message_id = self.uuid_factory()
            canonical_message = Message(
                id=canonical_message_id,
                tenant_id=tenant_id,
                conversation_thread_id=message.conversation_thread_id,
                external_message_id=send_result.provider_message_id,
                sender_type=ParticipantSenderType.MANAGER,
                direction=MessageDirection.OUTBOUND,
                sent_at=occurred_at,
                received_at=occurred_at,
                content_id=message.encrypted_content_id,
                reply_to_message_id=None,
                adapter_metadata=thread.adapter_metadata,
            )
            await uow.messages.append(canonical_message)
            status_event = MessageDeliveryStatusEvent(
                id=self.uuid_factory(),
                tenant_id=tenant_id,
                message_id=canonical_message_id,
                external_event_id=send_result.provider_message_id,
                occurred_at=occurred_at,
                delivery_status=DeliveryStatus.SENT,
                adapter_metadata=thread.adapter_metadata,
            )
            await uow.message_delivery_status_events.append(status_event)

            updated = replace(
                domain,
                status=OutboundMessageStatus.PROVIDER_ACCEPTED,
                provider_message_id=send_result.provider_message_id,
                completed_at=occurred_at,
                updated_at=occurred_at,
                version=domain.version + 1,
            )
            validate_outbound_message_transition(current=domain.status, target=updated.status)
            await self._persist_attempt(
                uow=uow,
                tenant_id=tenant_id,
                outbound_message_id=outbound_message_id,
                attempt_number=current.version,
                started_at=occurred_at,
                finished_at=occurred_at,
                outcome="succeeded",
                error_code=None,
            )
            await uow.outbound_messages.update(
                record=mappers.outbound_domain_to_record(updated),
                expected_version=current.version,
            )
            await append_required_audit_event(
                uow.audit_events,
                outbound_provider_accepted_event(
                    tenant_id=tenant_id,
                    outbound_message_id=outbound_message_id,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _call_provider(
        self,
        *,
        tenant_id: UUID,
        whatsapp_connection: WhatsAppCloudConnection,
        message: OutboundMessage,
        recipient_wa_id: str,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> tuple[WhatsAppSendResult | None, str | None]:
        if whatsapp_connection.access_token_ref is None:
            return None, "credentials_missing"

        secret = await self.credential_resolver.resolve_access_token(
            tenant_id=tenant_id,
            whatsapp_connection_id=whatsapp_connection.id,
            reference_key=whatsapp_connection.access_token_ref,
        )
        if secret is None:
            return None, "credentials_missing"

        uow = self.uow_factory()
        async with uow:
            encrypted = await uow.encrypted_contents.get_by_id(
                tenant_id=tenant_id,
                content_id=message.encrypted_content_id,
            )
            if encrypted is None:
                return None, "content_unavailable"
            decrypted = await self.content_encryption.load_and_decrypt(
                tenant_id=tenant_id,
                content_id=message.encrypted_content_id,
                purpose=ContentAccessPurpose.OUTBOUND_SEND,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                audit_event_id=self.uuid_factory(),
            )

        client = build_client_for_connection(
            graph_api_version=whatsapp_connection.graph_api_version,
            phone_number_id=whatsapp_connection.phone_number_id,
            access_token=secret.value.decode("utf-8"),
        )
        try:
            if message.kind is OutboundMessageKind.FREE_FORM_TEXT:
                body = (
                    decrypted.as_utf8_text()
                    if decrypted.encoding is ContentEncoding.UTF8
                    else decrypted.as_json_text()
                )
                return (
                    await client.send_text(
                        request=WhatsAppSendTextRequest(
                            recipient_wa_id=recipient_wa_id,
                            body=body,
                        )
                    ),
                    None,
                )
            template_record = None
            uow = self.uow_factory()
            async with uow:
                if message.provider_template_id is not None:
                    template_record = await uow.provider_message_templates.get_by_id(
                        tenant_id=tenant_id,
                        template_id=message.provider_template_id,
                    )
            if template_record is None:
                return None, "template_unavailable"
            parameters = _parse_template_parameters(decrypted)
            return (
                await client.send_template(
                    request=WhatsAppSendTemplateRequest(
                        recipient_wa_id=recipient_wa_id,
                        template_name=template_record.name,
                        language_code=template_record.language_code,
                        body_parameters=parameters,
                    )
                ),
                None,
            )
        except WhatsAppCloudApiClientError:
            return None, "delivery_unknown"
        except WhatsAppCloudApiResponseError as error:
            return None, error.error_code

    async def _last_customer_inbound_at(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        conversation_thread_id: UUID,
    ) -> datetime | None:
        from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

        if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
            return None
        from sqlalchemy import select

        from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType
        from closeros.infrastructure.canonical_orm import MessageRow

        statement = (
            select(MessageRow.received_at)
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.conversation_thread_id == conversation_thread_id,
                MessageRow.direction == MessageDirection.INBOUND.value,
                MessageRow.sender_type == ParticipantSenderType.CUSTOMER.value,
            )
            .order_by(MessageRow.received_at.desc())
            .limit(1)
        )
        return (await uow.session.execute(statement)).scalar_one_or_none()

    async def _persist_attempt(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        outbound_message_id: UUID,
        attempt_number: int,
        started_at: datetime,
        finished_at: datetime,
        outcome: str,
        error_code: str | None,
    ) -> None:
        await uow.outbound_delivery_attempts.add(
            record=OutboundDeliveryAttemptRecord(
                id=self.uuid_factory(),
                tenant_id=tenant_id,
                outbound_message_id=outbound_message_id,
                attempt_number=attempt_number,
                started_at=started_at,
                finished_at=finished_at,
                outcome=outcome,
                error_code=error_code,
            )
        )


def _parse_template_parameters(decrypted: DecryptedContent) -> tuple[str, ...]:
    if decrypted.encoding is ContentEncoding.JSON:
        document = json.loads(decrypted.as_json_text())
        if isinstance(document, dict):
            values = document.get("parameters")
            if isinstance(values, list):
                return tuple(str(item) for item in values)
    if decrypted.encoding is ContentEncoding.UTF8:
        return (decrypted.as_utf8_text(),)
    return ()
