"""Tenant-scoped conversation review query service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.analysis_query_service import AnalysisQueryService, AnalysisRunView
from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.follow_up_task_persistence import FollowUpTaskListFilter
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.product_audit import (
    conversation_detail_viewed_event,
    conversation_list_viewed_event,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.encrypted_content import ContentAccessPurpose, ContentEncoding
from closeros.domain.follow_up_task import FollowUpTask
from closeros.domain.identity import Role
from closeros.domain.privacy_redaction import SANITIZATION_POLICY_VERSION
from closeros.infrastructure.cursor_pagination import KeysetCursor, KeysetPage
from closeros.infrastructure.follow_up_task_mappers import record_to_domain
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.product_query_repositories import (
    ConversationListFilter,
    ConversationListItem,
    ProductQueryRepository,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_PRIVILEGED_CONVERSATION_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.COMPLIANCE_ADMIN})


@dataclass(frozen=True, slots=True)
class ConversationTimelineMessage:
    message_id: UUID
    sender_type: str
    direction: str
    sent_at: datetime
    received_at: datetime
    sanitized_text: str | None
    is_deleted: bool


class ConversationAccessDeniedError(PermissionError):
    """Raised when conversation access is denied."""


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    thread: ConversationThread
    manager_user_id: UUID | None
    messages: tuple[ConversationTimelineMessage, ...]
    analyses: tuple[AnalysisRunView, ...]
    tasks: tuple[FollowUpTask, ...]


def _is_manager_only(roles: frozenset[Role]) -> bool:
    return Role.MANAGER in roles and not roles.intersection(_PRIVILEGED_CONVERSATION_ROLES)


def _analyst_denied(roles: frozenset[Role]) -> bool:
    return Role.ANALYST in roles and not roles.intersection(_PRIVILEGED_CONVERSATION_ROLES)


class ConversationQueryService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        analysis_query_service: AnalysisQueryService,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._analysis_query_service = analysis_query_service
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def list_conversations(
        self,
        *,
        tenant_id: UUID,
        roles: frozenset[Role],
        user_id: UUID,
        filters: ConversationListFilter,
        limit: int,
        cursor: KeysetCursor | None,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> KeysetPage[ConversationListItem]:
        if _analyst_denied(roles):
            raise ConversationAccessDeniedError("access denied")
        manager_scope = user_id if _is_manager_only(roles) else None
        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise RuntimeError("conversation queries require sqlalchemy uow")
            page = await ProductQueryRepository(uow.session).list_conversations(
                filters=filters,
                manager_scope_user_id=manager_scope,
                limit=limit,
                cursor=cursor,
            )
            await append_required_audit_event(
                uow.audit_events,
                conversation_list_viewed_event(
                    tenant_id=tenant_id,
                    occurred_at=self._clock(),
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    affected_count=len(page.items),
                ),
            )
            await uow.commit()
        return page

    async def get_conversation_detail(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        roles: frozenset[Role],
        user_id: UUID,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> ConversationDetail | None:
        if _analyst_denied(roles):
            raise ConversationAccessDeniedError("access denied")
        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise RuntimeError("conversation queries require sqlalchemy uow")
            repo = ProductQueryRepository(uow.session)
            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=conversation_id,
            )
            if thread is None:
                return None
            if _is_manager_only(roles):
                attribution = await repo.load_attribution(
                    tenant_id=tenant_id,
                    window_end=self._clock(),
                )
                if attribution.get(conversation_id) != user_id:
                    raise ConversationAccessDeniedError("access denied")
            messages = await self._load_timeline(
                uow=uow,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                audit_context=audit_context,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            analyses = await self._analysis_query_service.list_runs(
                tenant_id=tenant_id,
                conversation_thread_id=conversation_id,
                limit=20,
            )
            tasks_page = await uow.follow_up_tasks.list_page(
                filters=FollowUpTaskListFilter(
                    tenant_id=tenant_id,
                    conversation_thread_id=conversation_id,
                ),
                limit=50,
                cursor=None,
            )
            attribution = await repo.load_attribution(
                tenant_id=tenant_id,
                window_end=self._clock(),
            )
            await append_required_audit_event(
                uow.audit_events,
                conversation_detail_viewed_event(
                    tenant_id=tenant_id,
                    conversation_thread_id=conversation_id,
                    occurred_at=self._clock(),
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return ConversationDetail(
            thread=thread,
            manager_user_id=attribution.get(conversation_id),
            messages=messages,
            analyses=analyses,
            tasks=tuple(record_to_domain(task) for task in tasks_page.items),
        )

    async def _load_timeline(
        self,
        *,
        uow: IntegratedUnitOfWork,
        tenant_id: UUID,
        conversation_id: UUID,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> tuple[ConversationTimelineMessage, ...]:
        if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
            return ()
        from sqlalchemy import select

        from closeros.infrastructure.canonical_orm import MessageDeletionEventRow, MessageRow

        rows = (
            (
                await uow.session.execute(
                    select(MessageRow)
                    .where(
                        MessageRow.tenant_id == tenant_id,
                        MessageRow.conversation_thread_id == conversation_id,
                    )
                    .order_by(MessageRow.received_at.asc(), MessageRow.id.asc())
                )
            )
            .scalars()
            .all()
        )
        deletion_result = await uow.session.execute(
            select(MessageDeletionEventRow.message_id)
            .join(MessageRow, MessageDeletionEventRow.message_id == MessageRow.id)
            .where(
                MessageDeletionEventRow.tenant_id == tenant_id,
                MessageRow.conversation_thread_id == conversation_id,
            )
        )
        deleted_ids = {row[0] for row in deletion_result.all()}
        timeline: list[ConversationTimelineMessage] = []
        occurred_at = self._clock()
        for row in rows:
            sanitized_text: str | None = None
            if row.content_id is not None:
                sanitization = await uow.content_sanitizations.get_completed_by_source(
                    tenant_id=tenant_id,
                    source_content_id=row.content_id,
                    policy_version=SANITIZATION_POLICY_VERSION,
                )
                if sanitization is not None and sanitization.sanitized_content_id is not None:
                    decrypted = await self._content_encryption.load_and_decrypt(
                        tenant_id=tenant_id,
                        content_id=sanitization.sanitized_content_id,
                        purpose=ContentAccessPurpose.CONVERSATION_REVIEW,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        audit_event_id=self._uuid_factory(),
                    )
                    if decrypted.encoding is ContentEncoding.UTF8:
                        sanitized_text = decrypted.as_utf8_text()
            timeline.append(
                ConversationTimelineMessage(
                    message_id=row.id,
                    sender_type=row.sender_type,
                    direction=row.direction,
                    sent_at=row.sent_at,
                    received_at=row.received_at,
                    sanitized_text=sanitized_text,
                    is_deleted=row.id in deleted_ids,
                )
            )
        return tuple(timeline)
