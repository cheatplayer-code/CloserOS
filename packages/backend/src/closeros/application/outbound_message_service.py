"""Application service for human-approved outbound messaging."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbound_persistence import (
    OutboundMessageNotFoundError,
    OutboundMessageVersionConflictError,
)
from closeros.application.outbox_persistence import DuplicateOutboxJobError
from closeros.application.whatsapp_audit import (
    outbound_draft_created_event,
    outbound_message_approved_event,
    outbound_message_queued_event,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.identity import Role
from closeros.domain.outbound_message import (
    OutboundMessage,
    OutboundMessageKind,
    OutboundMessageStatus,
    OutboundMessageTransitionError,
    outbound_resend_prohibited,
    validate_outbound_message_transition,
)
from closeros.domain.outbox import OutboxJobKind, OutboxJobReference, build_outbox_job
from closeros.infrastructure import outbound_mappers as mappers
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_SEND_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.MANAGER})
_PRIVILEGED_SEND_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})


class OutboundMessageServiceError(Exception):
    """Raised when outbound message operations cannot be completed."""


class OutboundMessageAccessDeniedError(OutboundMessageServiceError):
    """Raised when caller lacks permission for the operation."""


def _outbound_send_deduplication_key(*, message_id: UUID) -> str:
    return f"provider_message_send_{message_id}"


class OutboundMessageService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def create_draft(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        channel_connection_id: UUID,
        kind: OutboundMessageKind,
        plaintext: bytes,
        encoding: ContentEncoding,
        provider_template_id: UUID | None,
        created_by_user_id: UUID,
        actor_roles: frozenset[Role],
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> OutboundMessage:
        if not actor_roles.intersection(_SEND_ROLES):
            raise OutboundMessageAccessDeniedError("operation denied")
        if Role.ANALYST in actor_roles and not actor_roles.intersection(_PRIVILEGED_SEND_ROLES):
            raise OutboundMessageAccessDeniedError("operation denied")

        now = self._clock()
        message_id = self._uuid_factory()
        content_id = self._uuid_factory()

        uow = self._uow_factory()
        async with uow:
            if Role.MANAGER in actor_roles and not actor_roles.intersection(_PRIVILEGED_SEND_ROLES):
                await self._assert_manager_scope(
                    uow=uow,
                    tenant_id=tenant_id,
                    conversation_thread_id=conversation_thread_id,
                    manager_user_id=created_by_user_id,
                )

            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=conversation_thread_id,
            )
            if thread is None:
                raise OutboundMessageServiceError("conversation unavailable")

            await self._content_encryption.encrypt_and_persist(
                uow,
                content_id=content_id,
                tenant_id=tenant_id,
                kind=EncryptedContentKind.OUTBOUND_MESSAGE,
                encoding=encoding,
                plaintext=plaintext,
                created_at=now,
            )

            message = OutboundMessage(
                id=message_id,
                tenant_id=tenant_id,
                conversation_thread_id=conversation_thread_id,
                channel_connection_id=channel_connection_id,
                kind=kind,
                status=OutboundMessageStatus.DRAFT,
                encrypted_content_id=content_id,
                provider_template_id=provider_template_id,
                created_by_user_id=created_by_user_id,
                approved_by_user_id=None,
                provider_message_id=None,
                failure_code=None,
                created_at=now,
                approved_at=None,
                queued_at=None,
                sent_at=None,
                completed_at=None,
                updated_at=now,
                version=1,
            )
            await uow.outbound_messages.add(record=mappers.outbound_domain_to_record(message))
            await append_required_audit_event(
                uow.audit_events,
                outbound_draft_created_event(
                    tenant_id=tenant_id,
                    outbound_message_id=message_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    outbound_kind=kind.value,
                ),
            )
            await uow.commit()
        return message

    async def approve_and_queue(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
        approved_by_user_id: UUID,
        actor_roles: frozenset[Role],
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> OutboundMessage:
        if not actor_roles.intersection(_SEND_ROLES):
            raise OutboundMessageAccessDeniedError("operation denied")

        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.outbound_messages.get_by_id_for_update(
                tenant_id=tenant_id,
                message_id=message_id,
            )
            if current is None:
                raise OutboundMessageNotFoundError("outbound message not found")
            domain = mappers.outbound_record_to_domain(current)

            if Role.MANAGER in actor_roles and not actor_roles.intersection(_PRIVILEGED_SEND_ROLES):
                await self._assert_manager_scope(
                    uow=uow,
                    tenant_id=tenant_id,
                    conversation_thread_id=domain.conversation_thread_id,
                    manager_user_id=approved_by_user_id,
                )

            if domain.status is OutboundMessageStatus.QUEUED:
                return domain

            target_status = OutboundMessageStatus.QUEUED
            try:
                if domain.status is OutboundMessageStatus.DRAFT:
                    validate_outbound_message_transition(
                        current=domain.status,
                        target=OutboundMessageStatus.PENDING_APPROVAL,
                    )
                    validate_outbound_message_transition(
                        current=OutboundMessageStatus.PENDING_APPROVAL,
                        target=OutboundMessageStatus.APPROVED,
                    )
                    validate_outbound_message_transition(
                        current=OutboundMessageStatus.APPROVED,
                        target=target_status,
                    )
                elif domain.status is OutboundMessageStatus.PENDING_APPROVAL:
                    validate_outbound_message_transition(
                        current=domain.status,
                        target=OutboundMessageStatus.APPROVED,
                    )
                    validate_outbound_message_transition(
                        current=OutboundMessageStatus.APPROVED,
                        target=target_status,
                    )
                elif domain.status is OutboundMessageStatus.APPROVED:
                    validate_outbound_message_transition(
                        current=domain.status,
                        target=target_status,
                    )
                else:
                    raise OutboundMessageTransitionError("operation unavailable")
            except OutboundMessageTransitionError as error:
                raise OutboundMessageServiceError("operation unavailable") from error

            updated = replace(
                domain,
                status=target_status,
                approved_by_user_id=approved_by_user_id,
                approved_at=now,
                queued_at=now,
                updated_at=now,
                version=domain.version + 1,
            )
            OutboundMessage(
                id=updated.id,
                tenant_id=updated.tenant_id,
                conversation_thread_id=updated.conversation_thread_id,
                channel_connection_id=updated.channel_connection_id,
                kind=updated.kind,
                status=updated.status,
                encrypted_content_id=updated.encrypted_content_id,
                provider_template_id=updated.provider_template_id,
                created_by_user_id=updated.created_by_user_id,
                approved_by_user_id=updated.approved_by_user_id,
                provider_message_id=updated.provider_message_id,
                failure_code=updated.failure_code,
                created_at=updated.created_at,
                approved_at=updated.approved_at,
                queued_at=updated.queued_at,
                sent_at=updated.sent_at,
                completed_at=updated.completed_at,
                updated_at=updated.updated_at,
                version=updated.version,
            )
            try:
                persisted = await uow.outbound_messages.update(
                    record=mappers.outbound_domain_to_record(updated),
                    expected_version=expected_version,
                )
            except OutboundMessageVersionConflictError as error:
                raise OutboundMessageServiceError("operation unavailable") from error

            outbox_job_id = self._uuid_factory()
            with contextlib.suppress(DuplicateOutboxJobError):
                await uow.outbox_jobs.enqueue(
                    build_outbox_job(
                        job_id=outbox_job_id,
                        tenant_id=tenant_id,
                        job_kind=OutboxJobKind.PROVIDER_MESSAGE_SEND,
                        reference=OutboxJobReference(
                            resource_type="outbound_message",
                            resource_id=message_id,
                            schema_version=1,
                            tenant_id=tenant_id,
                        ),
                        deduplication_key=_outbound_send_deduplication_key(message_id=message_id),
                        created_at=now,
                    )
                )

            await append_required_audit_event(
                uow.audit_events,
                outbound_message_approved_event(
                    tenant_id=tenant_id,
                    outbound_message_id=message_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await append_required_audit_event(
                uow.audit_events,
                outbound_message_queued_event(
                    tenant_id=tenant_id,
                    outbound_message_id=message_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return mappers.outbound_record_to_domain(persisted)

    async def cancel(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
        actor_roles: frozenset[Role],
        expected_version: int,
    ) -> OutboundMessage:
        if not actor_roles.intersection(_SEND_ROLES):
            raise OutboundMessageAccessDeniedError("operation denied")

        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.outbound_messages.get_by_id_for_update(
                tenant_id=tenant_id,
                message_id=message_id,
            )
            if current is None:
                raise OutboundMessageNotFoundError("outbound message not found")
            domain = mappers.outbound_record_to_domain(current)
            if outbound_resend_prohibited(domain.status):
                raise OutboundMessageServiceError("operation unavailable")
            try:
                validate_outbound_message_transition(
                    current=domain.status,
                    target=OutboundMessageStatus.CANCELLED,
                )
            except OutboundMessageTransitionError as error:
                raise OutboundMessageServiceError("operation unavailable") from error

            updated = replace(
                domain,
                status=OutboundMessageStatus.CANCELLED,
                completed_at=now,
                updated_at=now,
                version=domain.version + 1,
            )
            OutboundMessage(
                id=updated.id,
                tenant_id=updated.tenant_id,
                conversation_thread_id=updated.conversation_thread_id,
                channel_connection_id=updated.channel_connection_id,
                kind=updated.kind,
                status=updated.status,
                encrypted_content_id=updated.encrypted_content_id,
                provider_template_id=updated.provider_template_id,
                created_by_user_id=updated.created_by_user_id,
                approved_by_user_id=updated.approved_by_user_id,
                provider_message_id=updated.provider_message_id,
                failure_code=updated.failure_code,
                created_at=updated.created_at,
                approved_at=updated.approved_at,
                queued_at=updated.queued_at,
                sent_at=updated.sent_at,
                completed_at=updated.completed_at,
                updated_at=updated.updated_at,
                version=updated.version,
            )
            try:
                persisted = await uow.outbound_messages.update(
                    record=mappers.outbound_domain_to_record(updated),
                    expected_version=expected_version,
                )
            except OutboundMessageVersionConflictError as error:
                raise OutboundMessageServiceError("operation unavailable") from error
            await uow.commit()
        return mappers.outbound_record_to_domain(persisted)

    async def get_message(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
        actor_roles: frozenset[Role],
        viewer_user_id: UUID | None,
    ) -> OutboundMessage | None:
        if (
            Role.ANALYST in actor_roles
            and Role.COMPLIANCE_ADMIN not in actor_roles
            and not actor_roles.intersection(_PRIVILEGED_SEND_ROLES)
        ):
            raise OutboundMessageAccessDeniedError("operation denied")

        uow = self._uow_factory()
        async with uow:
            record = await uow.outbound_messages.get_by_id(
                tenant_id=tenant_id,
                message_id=message_id,
            )
            if record is None:
                return None
            domain = mappers.outbound_record_to_domain(record)
            if Role.MANAGER in actor_roles and not actor_roles.intersection(_PRIVILEGED_SEND_ROLES):
                if viewer_user_id is None:
                    raise OutboundMessageAccessDeniedError("operation denied")
                await self._assert_manager_scope(
                    uow=uow,
                    tenant_id=tenant_id,
                    conversation_thread_id=domain.conversation_thread_id,
                    manager_user_id=viewer_user_id,
                )
        return domain

    async def _assert_manager_scope(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        manager_user_id: UUID,
    ) -> None:
        if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
            raise OutboundMessageAccessDeniedError("operation denied")
        from sqlalchemy import select

        from closeros.infrastructure.canonical_orm import ManagerAssignmentRow

        statement = select(ManagerAssignmentRow.manager_user_id).where(
            ManagerAssignmentRow.tenant_id == tenant_id,
            ManagerAssignmentRow.conversation_thread_id == conversation_thread_id,
        )
        result = (await uow.session.execute(statement)).scalar_one_or_none()
        if result != manager_user_id:
            raise OutboundMessageAccessDeniedError("operation denied")
