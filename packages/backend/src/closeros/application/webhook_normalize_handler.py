"""Outbox handler that normalizes encrypted provider webhook payloads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.canonical_persistence import (
    CanonicalRecordNotFoundError,
    DuplicateMessageDeletionEventError,
    DuplicateMessageDeliveryStatusEventError,
    DuplicateMessageEditEventError,
    DuplicateMessageError,
)
from closeros.application.content_audit import (
    content_encrypted_accessed_event,
    message_edit_stored_event,
    raw_message_stored_event,
)
from closeros.application.content_encryption_service import (
    ContentAccessDeniedError,
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
)
from closeros.application.ingestion_audit import (
    provider_code_for_kind,
    webhook_normalization_failed_event,
    webhook_normalized_event,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.application.provider_adapter_registry import (
    ProviderAdapterRegistry,
    UnknownProviderAdapterError,
)
from closeros.application.provider_ports import ProviderPayloadError
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import WebhookProcessingStatus
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.message import Message
from closeros.domain.message_events import (
    MessageDeletionEvent,
    MessageDeliveryStatusEvent,
    MessageEditEvent,
)
from closeros.domain.normalized_operations import (
    NormalizedDeliveryStatusChanged,
    NormalizedMessageDeleted,
    NormalizedMessageEdited,
    NormalizedMessageReceived,
    NormalizedOperation,
)
from closeros.domain.outbox import (
    OutboxErrorCode,
    OutboxJob,
    OutboxJobKind,
    OutboxJobReference,
    build_outbox_job,
)


class WebhookNormalizeHandlerError(Exception):
    """Controlled webhook normalization failure surfaced to the outbox processor."""

    def __init__(
        self,
        *,
        error_code: OutboxErrorCode,
        permanent: bool,
    ) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("webhook normalization failed")


_UuidFactory = Callable[[], UUID]
_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


def _content_redact_deduplication_key(*, resource_id: UUID) -> str:
    return f"content_redact_{resource_id}"


def _content_type_for_encoding(encoding: ContentEncoding) -> str:
    if encoding is ContentEncoding.JSON:
        return "application/json"
    if encoding is ContentEncoding.UTF8:
        return "text/plain"
    return "application/octet-stream"


@dataclass(frozen=True, slots=True)
class WebhookNormalizeHandler:
    """Normalizes verified provider payloads into canonical conversation entities."""

    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    adapter_registry: ProviderAdapterRegistry
    atomic_commands: AtomicContentCommandService
    service_actor_id: UUID
    uuid_factory: _UuidFactory

    def __repr__(self) -> str:
        return "WebhookNormalizeHandler()"

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=True,
            )

        tenant_id = job.tenant_id
        webhook_event_id = job.reference.resource_id
        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)

        uow = self.uow_factory()
        async with uow:
            try:
                webhook_event = await uow.webhook_events.get_by_id(
                    tenant_id=tenant_id,
                    event_id=webhook_event_id,
                )
                if webhook_event is None:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    )

                if webhook_event.processing_status is WebhookProcessingStatus.PROCESSED:
                    return

                connection = await uow.channel_connections.get_by_id(
                    tenant_id=tenant_id,
                    connection_id=webhook_event.channel_connection_id,
                )
                if connection is None:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    )

                content_id = webhook_event.encrypted_payload_content_id
                if content_id is None:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                        permanent=True,
                    )

                encrypted = await uow.encrypted_contents.get_by_id(
                    tenant_id=tenant_id,
                    content_id=content_id,
                )
                if encrypted is None:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    )

                if encrypted.kind is not EncryptedContentKind.PROVIDER_PAYLOAD:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                        permanent=True,
                    )

                try:
                    decrypted = self.content_encryption.data_key_cryptography.decrypt_content(
                        encrypted=encrypted,
                    )
                except Exception as error:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                        permanent=False,
                    ) from error

                await append_required_audit_event(
                    uow.audit_events,
                    content_encrypted_accessed_event(
                        tenant_id=tenant_id,
                        content_id=content_id,
                        kind=encrypted.kind,
                        purpose=ContentAccessPurpose.WEBHOOK_NORMALIZATION,
                        key_version=encrypted.key_version,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )

                try:
                    adapter = self.adapter_registry.resolve(connection.provider)
                except UnknownProviderAdapterError as error:
                    raise WebhookNormalizeHandlerError(
                        error_code=OutboxErrorCode.ADAPTER_UNAVAILABLE,
                        permanent=False,
                    ) from error

                try:
                    operations = adapter.normalize_payload(
                        decrypted_payload=decrypted.as_bytes(),
                        content_type=_content_type_for_encoding(decrypted.encoding),
                    )
                except ProviderPayloadError as error:
                    message = str(error)
                    if "unsupported" in message.lower():
                        code = OutboxErrorCode.UNSUPPORTED_OPERATION
                    else:
                        code = OutboxErrorCode.MALFORMED_PROVIDER_EVENT
                    raise WebhookNormalizeHandlerError(
                        error_code=code,
                        permanent=True,
                    ) from error

                for operation in operations:
                    await self._persist_operation(
                        uow=uow,
                        tenant_id=tenant_id,
                        channel_connection_id=connection.id,
                        operation=operation,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                    )

                await uow.webhook_events.update_processing_status(
                    tenant_id=tenant_id,
                    event_id=webhook_event_id,
                    processing_status=WebhookProcessingStatus.PROCESSED,
                    processed_at=occurred_at,
                )
                await append_required_audit_event(
                    uow.audit_events,
                    webhook_normalized_event(
                        tenant_id=tenant_id,
                        webhook_event_id=webhook_event_id,
                        provider_code=provider_code_for_kind(connection.provider),
                        operation_count=len(operations),
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.commit()
            except WebhookNormalizeHandlerError as error:
                await uow.rollback()
                provider_code = (
                    provider_code_for_kind(connection.provider)
                    if "connection" in locals() and connection is not None
                    else "unknown"
                )
                await self._record_normalization_failure(
                    tenant_id=tenant_id,
                    webhook_event_id=webhook_event_id,
                    provider_code=provider_code,
                    reason_code=error.error_code.value,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    permanent=error.permanent,
                )
                raise
            except (
                ContentEncryptionUnavailableError,
                ContentAccessDeniedError,
                CanonicalRecordNotFoundError,
                DuplicateMessageError,
                DuplicateMessageEditEventError,
                DuplicateMessageDeletionEventError,
                DuplicateMessageDeliveryStatusEventError,
                DuplicateOutboxJobError,
            ) as error:
                await uow.rollback()
                raise WebhookNormalizeHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error
            except Exception as error:
                await uow.rollback()
                raise WebhookNormalizeHandlerError(
                    error_code=OutboxErrorCode.HANDLER_FAILED,
                    permanent=False,
                ) from error

    async def _record_normalization_failure(
        self,
        *,
        tenant_id: UUID,
        webhook_event_id: UUID,
        provider_code: str,
        reason_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
        permanent: bool,
    ) -> None:
        if not permanent:
            return

        uow = self.uow_factory()
        async with uow:
            try:
                await append_required_audit_event(
                    uow.audit_events,
                    webhook_normalization_failed_event(
                        tenant_id=tenant_id,
                        webhook_event_id=webhook_event_id,
                        provider_code=provider_code,
                        reason_code=reason_code,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                    ),
                )
                await uow.webhook_events.update_processing_status(
                    tenant_id=tenant_id,
                    event_id=webhook_event_id,
                    processing_status=WebhookProcessingStatus.FAILED,
                    processed_at=occurred_at,
                )
                await uow.commit()
            except Exception:
                await uow.rollback()

    async def _persist_operation(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        operation: NormalizedOperation,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        if isinstance(operation, NormalizedMessageReceived):
            await self._persist_message_received(
                uow=uow,
                tenant_id=tenant_id,
                channel_connection_id=channel_connection_id,
                operation=operation,
                occurred_at=occurred_at,
                audit_context=audit_context,
            )
            return

        if isinstance(operation, NormalizedMessageEdited):
            await self._persist_message_edited(
                uow=uow,
                tenant_id=tenant_id,
                channel_connection_id=channel_connection_id,
                operation=operation,
                occurred_at=occurred_at,
                audit_context=audit_context,
            )
            return

        if isinstance(operation, NormalizedMessageDeleted):
            await self._persist_message_deleted(
                uow=uow,
                tenant_id=tenant_id,
                channel_connection_id=channel_connection_id,
                operation=operation,
            )
            return

        if isinstance(operation, NormalizedDeliveryStatusChanged):
            await self._persist_delivery_status_changed(
                uow=uow,
                tenant_id=tenant_id,
                channel_connection_id=channel_connection_id,
                operation=operation,
            )
            return

        raise WebhookNormalizeHandlerError(
            error_code=OutboxErrorCode.UNSUPPORTED_OPERATION,
            permanent=True,
        )

    async def _get_or_create_thread(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        external_conversation_id: str,
        adapter_metadata: AdapterMetadata,
        occurred_at: datetime,
    ) -> ConversationThread:
        existing = await uow.conversation_threads.get_by_external_conversation_id(
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=external_conversation_id,
        )
        if existing is not None:
            return existing

        thread = ConversationThread(
            id=self.uuid_factory(),
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=external_conversation_id,
            sales_case_id=None,
            lifecycle_status=None,
            adapter_metadata=adapter_metadata,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        await uow.conversation_threads.add(thread)
        return thread

    async def _persist_message_received(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        operation: NormalizedMessageReceived,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        thread = await self._get_or_create_thread(
            uow=uow,
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=operation.external_conversation_id,
            adapter_metadata=operation.adapter_metadata,
            occurred_at=occurred_at,
        )

        existing_message = await uow.messages.get_by_external_message_id(
            tenant_id=tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=operation.external_message_id,
        )
        if existing_message is not None:
            return

        reply_to_message_id: UUID | None = None
        if operation.reply_to_external_message_id is not None:
            parent = await uow.messages.get_by_external_message_id(
                tenant_id=tenant_id,
                conversation_thread_id=thread.id,
                external_message_id=operation.reply_to_external_message_id,
            )
            if parent is None:
                raise WebhookNormalizeHandlerError(
                    error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                    permanent=True,
                )
            reply_to_message_id = parent.id

        message_id = self.uuid_factory()
        content_id = self.uuid_factory()
        outbox_job_id = self.uuid_factory()
        audit_event_id = self.uuid_factory()

        encrypted = await self.content_encryption.encrypt_and_persist(
            uow,
            content_id=content_id,
            tenant_id=tenant_id,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=operation.raw_message_bytes,
            created_at=occurred_at,
        )
        message = Message(
            id=message_id,
            tenant_id=tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=operation.external_message_id,
            sender_type=operation.sender_type,
            direction=operation.direction,
            sent_at=operation.sent_at,
            received_at=operation.received_at,
            content_id=content_id,
            reply_to_message_id=reply_to_message_id,
            adapter_metadata=operation.adapter_metadata,
        )
        await uow.messages.append(message)
        await uow.outbox_jobs.enqueue(
            build_outbox_job(
                job_id=outbox_job_id,
                tenant_id=tenant_id,
                job_kind=OutboxJobKind.CONTENT_REDACT,
                reference=OutboxJobReference(
                    resource_type="message",
                    resource_id=message_id,
                    schema_version=1,
                    tenant_id=tenant_id,
                    secondary_id=content_id,
                ),
                deduplication_key=_content_redact_deduplication_key(resource_id=message_id),
                created_at=occurred_at,
            )
        )
        await append_required_audit_event(
            uow.audit_events,
            raw_message_stored_event(
                tenant_id=tenant_id,
                message_id=message_id,
                content_id=content_id,
                key_version=encrypted.key_version,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                event_id=audit_event_id,
            ),
        )

    async def _persist_message_edited(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        operation: NormalizedMessageEdited,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        thread = await self._get_or_create_thread(
            uow=uow,
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=operation.external_conversation_id,
            adapter_metadata=operation.adapter_metadata,
            occurred_at=occurred_at,
        )
        message = await uow.messages.get_by_external_message_id(
            tenant_id=tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=operation.external_message_id,
        )
        if message is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )

        edit_event_id = self.uuid_factory()
        content_id = self.uuid_factory()
        outbox_job_id = self.uuid_factory()
        audit_event_id = self.uuid_factory()

        encrypted = await self.content_encryption.encrypt_and_persist(
            uow,
            content_id=content_id,
            tenant_id=tenant_id,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=operation.replacement_bytes,
            created_at=occurred_at,
        )
        edit_event = MessageEditEvent(
            id=edit_event_id,
            tenant_id=tenant_id,
            message_id=message.id,
            external_event_id=operation.external_event_id,
            occurred_at=operation.occurred_at,
            content_id=content_id,
            adapter_metadata=operation.adapter_metadata,
        )
        try:
            await uow.message_edit_events.append(edit_event)
        except DuplicateMessageEditEventError:
            return

        await uow.outbox_jobs.enqueue(
            build_outbox_job(
                job_id=outbox_job_id,
                tenant_id=tenant_id,
                job_kind=OutboxJobKind.CONTENT_REDACT,
                reference=OutboxJobReference(
                    resource_type="message_edit_event",
                    resource_id=edit_event_id,
                    schema_version=1,
                    tenant_id=tenant_id,
                    secondary_id=content_id,
                ),
                deduplication_key=_content_redact_deduplication_key(resource_id=edit_event_id),
                created_at=occurred_at,
            )
        )
        await append_required_audit_event(
            uow.audit_events,
            message_edit_stored_event(
                tenant_id=tenant_id,
                edit_event_id=edit_event_id,
                message_id=message.id,
                content_id=content_id,
                key_version=encrypted.key_version,
                occurred_at=operation.occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                event_id=audit_event_id,
            ),
        )

    async def _persist_message_deleted(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        operation: NormalizedMessageDeleted,
    ) -> None:
        thread = await uow.conversation_threads.get_by_external_conversation_id(
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=operation.external_conversation_id,
        )
        if thread is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )

        message = await uow.messages.get_by_external_message_id(
            tenant_id=tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=operation.external_message_id,
        )
        if message is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )

        deletion_event = MessageDeletionEvent(
            id=self.uuid_factory(),
            tenant_id=tenant_id,
            message_id=message.id,
            external_event_id=operation.external_event_id,
            occurred_at=operation.occurred_at,
            adapter_metadata=operation.adapter_metadata,
        )
        try:
            await uow.message_deletion_events.append(deletion_event)
        except DuplicateMessageDeletionEventError:
            return

    async def _persist_delivery_status_changed(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        channel_connection_id: UUID,
        operation: NormalizedDeliveryStatusChanged,
    ) -> None:
        thread = await uow.conversation_threads.get_by_external_conversation_id(
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            external_conversation_id=operation.external_conversation_id,
        )
        if thread is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )

        message = await uow.messages.get_by_external_message_id(
            tenant_id=tenant_id,
            conversation_thread_id=thread.id,
            external_message_id=operation.external_message_id,
        )
        if message is None:
            raise WebhookNormalizeHandlerError(
                error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                permanent=True,
            )

        status_event = MessageDeliveryStatusEvent(
            id=self.uuid_factory(),
            tenant_id=tenant_id,
            message_id=message.id,
            external_event_id=operation.external_event_id,
            occurred_at=operation.occurred_at,
            delivery_status=operation.delivery_status,
            adapter_metadata=operation.adapter_metadata,
        )
        try:
            await uow.message_delivery_status_events.append(status_event)
        except DuplicateMessageDeliveryStatusEventError:
            return
