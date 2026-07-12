"""Atomic commands combining encrypted content, canonical writes, outbox, and audit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.canonical_persistence import (
    CanonicalRecordNotFoundError,
    DuplicateMessageEditEventError,
    DuplicateMessageError,
)
from closeros.application.content_audit import (
    message_edit_stored_event,
    provider_payload_attached_event,
    raw_message_stored_event,
)
from closeros.application.content_encryption_service import (
    ContentEncryptionService,
    ContentEncryptionUnavailableError,
    ContentTenantUnavailableError,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import MessageDirection, ParticipantSenderType
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.message import Message
from closeros.domain.message_events import MessageEditEvent
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job


class AtomicContentCommandError(Exception):
    """Base class for safe atomic encrypted-content command failures."""


class AtomicContentCommandUnavailableError(AtomicContentCommandError):
    """Raised when an atomic encrypted-content command cannot complete."""


_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _raise_unavailable() -> NoReturn:
    raise AtomicContentCommandUnavailableError("atomic content command failed")


def _content_redact_deduplication_key(*, resource_id: UUID) -> str:
    return f"content_redact_{resource_id}"


def _webhook_normalize_deduplication_key(*, webhook_event_id: UUID) -> str:
    return f"webhook_normalize_{webhook_event_id}"


@dataclass(frozen=True, slots=True)
class StoreRawMessageResult:
    content_id: UUID
    message_id: UUID
    outbox_job_id: UUID


@dataclass(frozen=True, slots=True)
class StoreMessageEditResult:
    content_id: UUID
    edit_event_id: UUID
    outbox_job_id: UUID


@dataclass(frozen=True, slots=True)
class AttachProviderPayloadResult:
    content_id: UUID
    webhook_event_id: UUID
    outbox_job_id: UUID


@dataclass(frozen=True, slots=True)
class AtomicContentCommandService:
    """Persists encrypted content with canonical entities and outbox jobs atomically."""

    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService

    def __repr__(self) -> str:
        return "AtomicContentCommandService()"

    async def store_raw_message(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        message_id: UUID,
        outbox_job_id: UUID,
        audit_event_id: UUID,
        conversation_thread_id: UUID,
        external_message_id: str,
        sender_type: ParticipantSenderType,
        direction: MessageDirection,
        sent_at: datetime,
        received_at: datetime,
        reply_to_message_id: UUID | None,
        adapter_metadata: AdapterMetadata,
        plaintext: bytes,
        created_at: datetime,
        occurred_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> StoreRawMessageResult:
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_message_id = _validate_uuid(message_id, "message_id")
        validated_outbox_job_id = _validate_uuid(outbox_job_id, "outbox_job_id")
        validated_audit_event_id = _validate_uuid(audit_event_id, "audit_event_id")
        validated_thread_id = _validate_uuid(conversation_thread_id, "conversation_thread_id")
        validated_created_at = _validate_timezone_aware_datetime(created_at, "created_at")
        validated_occurred_at = _validate_timezone_aware_datetime(occurred_at, "occurred_at")

        uow = self.uow_factory()
        async with uow:
            try:
                encrypted = await self.content_encryption.encrypt_and_persist(
                    uow,
                    content_id=validated_content_id,
                    tenant_id=validated_tenant_id,
                    kind=EncryptedContentKind.RAW_MESSAGE,
                    encoding=ContentEncoding.UTF8,
                    plaintext=plaintext,
                    created_at=validated_created_at,
                )
                message = Message(
                    id=validated_message_id,
                    tenant_id=validated_tenant_id,
                    conversation_thread_id=validated_thread_id,
                    external_message_id=external_message_id,
                    sender_type=sender_type,
                    direction=direction,
                    sent_at=sent_at,
                    received_at=received_at,
                    content_id=validated_content_id,
                    reply_to_message_id=reply_to_message_id,
                    adapter_metadata=adapter_metadata,
                )
                await uow.messages.append(message)
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=validated_outbox_job_id,
                        tenant_id=validated_tenant_id,
                        job_kind=OutboxJobKind.CONTENT_REDACT,
                        reference=OutboxJobReference(
                            resource_type="message",
                            resource_id=validated_message_id,
                            schema_version=1,
                            tenant_id=validated_tenant_id,
                            secondary_id=validated_content_id,
                        ),
                        deduplication_key=_content_redact_deduplication_key(
                            resource_id=validated_message_id,
                        ),
                        created_at=validated_created_at,
                    )
                )
                await append_required_audit_event(
                    uow.audit_events,
                    raw_message_stored_event(
                        tenant_id=validated_tenant_id,
                        message_id=validated_message_id,
                        content_id=validated_content_id,
                        key_version=encrypted.key_version,
                        occurred_at=validated_occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=validated_audit_event_id,
                    ),
                )
                await uow.commit()
            except (
                ContentEncryptionUnavailableError,
                ContentTenantUnavailableError,
                DuplicateMessageError,
                DuplicateOutboxJobError,
            ) as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error
            except Exception as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error

        return StoreRawMessageResult(
            content_id=validated_content_id,
            message_id=validated_message_id,
            outbox_job_id=validated_outbox_job_id,
        )

    async def store_message_edit(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        edit_event_id: UUID,
        message_id: UUID,
        outbox_job_id: UUID,
        audit_event_id: UUID,
        external_event_id: str,
        occurred_at: datetime,
        adapter_metadata: AdapterMetadata,
        plaintext: bytes,
        created_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> StoreMessageEditResult:
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_edit_event_id = _validate_uuid(edit_event_id, "edit_event_id")
        validated_message_id = _validate_uuid(message_id, "message_id")
        validated_outbox_job_id = _validate_uuid(outbox_job_id, "outbox_job_id")
        validated_audit_event_id = _validate_uuid(audit_event_id, "audit_event_id")
        validated_occurred_at = _validate_timezone_aware_datetime(occurred_at, "occurred_at")
        validated_created_at = _validate_timezone_aware_datetime(created_at, "created_at")

        uow = self.uow_factory()
        async with uow:
            try:
                encrypted = await self.content_encryption.encrypt_and_persist(
                    uow,
                    content_id=validated_content_id,
                    tenant_id=validated_tenant_id,
                    kind=EncryptedContentKind.RAW_MESSAGE,
                    encoding=ContentEncoding.UTF8,
                    plaintext=plaintext,
                    created_at=validated_created_at,
                )
                edit_event = MessageEditEvent(
                    id=validated_edit_event_id,
                    tenant_id=validated_tenant_id,
                    message_id=validated_message_id,
                    external_event_id=external_event_id,
                    occurred_at=validated_occurred_at,
                    content_id=validated_content_id,
                    adapter_metadata=adapter_metadata,
                )
                await uow.message_edit_events.append(edit_event)
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=validated_outbox_job_id,
                        tenant_id=validated_tenant_id,
                        job_kind=OutboxJobKind.CONTENT_REDACT,
                        reference=OutboxJobReference(
                            resource_type="message_edit_event",
                            resource_id=validated_edit_event_id,
                            schema_version=1,
                            tenant_id=validated_tenant_id,
                            secondary_id=validated_content_id,
                        ),
                        deduplication_key=_content_redact_deduplication_key(
                            resource_id=validated_edit_event_id,
                        ),
                        created_at=validated_created_at,
                    )
                )
                await append_required_audit_event(
                    uow.audit_events,
                    message_edit_stored_event(
                        tenant_id=validated_tenant_id,
                        edit_event_id=validated_edit_event_id,
                        message_id=validated_message_id,
                        content_id=validated_content_id,
                        key_version=encrypted.key_version,
                        occurred_at=validated_occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=validated_audit_event_id,
                    ),
                )
                await uow.commit()
            except (
                ContentEncryptionUnavailableError,
                ContentTenantUnavailableError,
                DuplicateMessageEditEventError,
                DuplicateOutboxJobError,
            ) as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error
            except Exception as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error

        return StoreMessageEditResult(
            content_id=validated_content_id,
            edit_event_id=validated_edit_event_id,
            outbox_job_id=validated_outbox_job_id,
        )

    async def attach_provider_payload(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        webhook_event_id: UUID,
        outbox_job_id: UUID,
        audit_event_id: UUID,
        plaintext: bytes,
        encoding: ContentEncoding,
        created_at: datetime,
        occurred_at: datetime,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> AttachProviderPayloadResult:
        validated_tenant_id = _validate_uuid(tenant_id, "tenant_id")
        validated_content_id = _validate_uuid(content_id, "content_id")
        validated_webhook_event_id = _validate_uuid(webhook_event_id, "webhook_event_id")
        validated_outbox_job_id = _validate_uuid(outbox_job_id, "outbox_job_id")
        validated_audit_event_id = _validate_uuid(audit_event_id, "audit_event_id")
        validated_created_at = _validate_timezone_aware_datetime(created_at, "created_at")
        validated_occurred_at = _validate_timezone_aware_datetime(occurred_at, "occurred_at")

        if not isinstance(encoding, ContentEncoding):
            raise TypeError("encoding must be a ContentEncoding")

        uow = self.uow_factory()
        async with uow:
            try:
                existing_event = await uow.webhook_events.get_by_id(
                    tenant_id=validated_tenant_id,
                    event_id=validated_webhook_event_id,
                )
                if existing_event is None:
                    raise CanonicalRecordNotFoundError("webhook event not found")

                encrypted = await self.content_encryption.encrypt_and_persist(
                    uow,
                    content_id=validated_content_id,
                    tenant_id=validated_tenant_id,
                    kind=EncryptedContentKind.PROVIDER_PAYLOAD,
                    encoding=encoding,
                    plaintext=plaintext,
                    created_at=validated_created_at,
                )
                await uow.webhook_events.attach_encrypted_payload(
                    tenant_id=validated_tenant_id,
                    event_id=validated_webhook_event_id,
                    encrypted_payload_content_id=validated_content_id,
                )
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=validated_outbox_job_id,
                        tenant_id=validated_tenant_id,
                        job_kind=OutboxJobKind.WEBHOOK_NORMALIZE,
                        reference=OutboxJobReference(
                            resource_type="webhook_event",
                            resource_id=validated_webhook_event_id,
                            schema_version=1,
                            tenant_id=validated_tenant_id,
                            secondary_id=validated_content_id,
                        ),
                        deduplication_key=_webhook_normalize_deduplication_key(
                            webhook_event_id=validated_webhook_event_id,
                        ),
                        created_at=validated_created_at,
                    )
                )
                await append_required_audit_event(
                    uow.audit_events,
                    provider_payload_attached_event(
                        tenant_id=validated_tenant_id,
                        webhook_event_id=validated_webhook_event_id,
                        content_id=validated_content_id,
                        key_version=encrypted.key_version,
                        occurred_at=validated_occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=validated_audit_event_id,
                    ),
                )
                await uow.commit()
            except (
                ContentEncryptionUnavailableError,
                ContentTenantUnavailableError,
                CanonicalRecordNotFoundError,
                DuplicateOutboxJobError,
            ) as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error
            except Exception as error:
                await uow.rollback()
                raise AtomicContentCommandUnavailableError(
                    "atomic content command failed"
                ) from error

        return AttachProviderPayloadResult(
            content_id=validated_content_id,
            webhook_event_id=validated_webhook_event_id,
            outbox_job_id=validated_outbox_job_id,
        )
