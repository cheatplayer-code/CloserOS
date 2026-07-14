"""Application service for structured buyer memory lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.clock import Clock, SystemClock
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.reply_suggestion_audit import (
    buyer_memory_confirmed_event,
    buyer_memory_corrected_event,
    buyer_memory_deleted_event,
)
from closeros.application.tenant_context import TenantContext
from closeros.domain.audit import AuditActorType
from closeros.domain.buyer_memory import (
    DEFAULT_INFERENCE_TTL_SECONDS,
    BuyerMemoryError,
    BuyerMemoryFact,
    BuyerMemoryFactStatus,
    BuyerMemoryFactType,
    select_effective_memory_facts,
)
from closeros.domain.identity import Role
from closeros.domain.reply_suggestion import ReplySuggestionAccessDeniedError
from closeros.infrastructure.canonical_orm import ManagerAssignmentRow
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]

_MANAGE_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD, Role.MANAGER})
_PRIVILEGED_ROLES = frozenset({Role.OWNER, Role.SALES_HEAD})


class BuyerMemoryAccessDeniedError(ReplySuggestionAccessDeniedError):
    """Raised when buyer memory access is denied."""


class BuyerMemoryServiceError(BuyerMemoryError):
    """Raised when buyer memory operations cannot be completed."""


def _require_read(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_MANAGE_ROLES):
        raise BuyerMemoryAccessDeniedError("access denied")


def _require_mutate(context: TenantContext) -> None:
    if not context.membership.roles.intersection(_MANAGE_ROLES):
        raise BuyerMemoryAccessDeniedError("access denied")


def _is_manager_only(roles: frozenset[Role]) -> bool:
    return Role.MANAGER in roles and not roles.intersection(_PRIVILEGED_ROLES)


class BuyerMemoryService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        clock: Clock | None = None,
        uuid_factory: _UuidFactory | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock or SystemClock()
        self._uuid_factory = uuid_factory or uuid4

    async def list_effective_for_thread(
        self,
        *,
        context: TenantContext,
        conversation_thread_id: UUID,
    ) -> tuple[BuyerMemoryFact, ...]:
        _require_read(context)
        await self._assert_thread_access(
            context=context,
            conversation_thread_id=conversation_thread_id,
        )
        async with self._uow_factory() as uow:
            facts = await uow.buyer_memory_facts.list_for_thread(
                tenant_id=context.tenant.id,
                conversation_thread_id=conversation_thread_id,
            )
        return select_effective_memory_facts(facts, now=self._clock.now())

    async def list_all_for_thread(
        self,
        *,
        context: TenantContext,
        conversation_thread_id: UUID,
    ) -> Sequence[BuyerMemoryFact]:
        _require_read(context)
        await self._assert_thread_access(
            context=context,
            conversation_thread_id=conversation_thread_id,
        )
        async with self._uow_factory() as uow:
            return await uow.buyer_memory_facts.list_for_thread(
                tenant_id=context.tenant.id,
                conversation_thread_id=conversation_thread_id,
            )

    async def list_effective_for_lead(
        self,
        *,
        context: TenantContext,
        lead_id: UUID,
    ) -> tuple[BuyerMemoryFact, ...]:
        _require_read(context)
        async with self._uow_factory() as uow:
            facts = await uow.buyer_memory_facts.list_for_lead(
                tenant_id=context.tenant.id,
                lead_id=lead_id,
            )
        return select_effective_memory_facts(facts, now=self._clock.now())

    async def list_all_for_lead(
        self,
        *,
        context: TenantContext,
        lead_id: UUID,
    ) -> Sequence[BuyerMemoryFact]:
        _require_read(context)
        async with self._uow_factory() as uow:
            return await uow.buyer_memory_facts.list_for_lead(
                tenant_id=context.tenant.id,
                lead_id=lead_id,
            )

    async def confirm(
        self,
        *,
        context: TenantContext,
        fact_id: UUID,
        source_message_id: UUID,
        audit_context: AuditContext,
    ) -> BuyerMemoryFact:
        _require_mutate(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            fact = await uow.buyer_memory_facts.get(
                tenant_id=context.tenant.id,
                fact_id=fact_id,
            )
            if fact is None:
                raise BuyerMemoryServiceError("fact unavailable")
            await self._assert_thread_access(
                context=context,
                conversation_thread_id=fact.conversation_thread_id,
            )
            updated = BuyerMemoryFact(
                id=fact.id,
                tenant_id=fact.tenant_id,
                conversation_thread_id=fact.conversation_thread_id,
                lead_id=fact.lead_id,
                fact_type=fact.fact_type,
                normalized_value=fact.normalized_value,
                display_value=fact.display_value,
                status=BuyerMemoryFactStatus.CONFIRMED,
                confidence_basis_points=fact.confidence_basis_points,
                source_message_id=source_message_id,
                source_analysis_id=fact.source_analysis_id,
                supersedes_fact_id=fact.supersedes_fact_id,
                observed_at=fact.observed_at,
                confirmed_at=now,
                expires_at=None,
                created_at=fact.created_at,
                updated_at=now,
                version=fact.version + 1,
            )
            persisted = await uow.buyer_memory_facts.save(updated)
            await append_required_audit_event(
                uow.audit_events,
                buyer_memory_confirmed_event(
                    tenant_id=context.tenant.id,
                    fact_id=fact_id,
                    fact_type=fact.fact_type.value,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return persisted

    async def correct(
        self,
        *,
        context: TenantContext,
        fact_id: UUID,
        normalized_value: str,
        display_value: str,
        source_message_id: UUID | None,
        audit_context: AuditContext,
    ) -> BuyerMemoryFact:
        _require_mutate(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            prior = await uow.buyer_memory_facts.get(
                tenant_id=context.tenant.id,
                fact_id=fact_id,
            )
            if prior is None:
                raise BuyerMemoryServiceError("fact unavailable")
            await self._assert_thread_access(
                context=context,
                conversation_thread_id=prior.conversation_thread_id,
            )
            corrected = BuyerMemoryFact(
                id=self._uuid_factory(),
                tenant_id=prior.tenant_id,
                conversation_thread_id=prior.conversation_thread_id,
                lead_id=prior.lead_id,
                fact_type=prior.fact_type,
                normalized_value=normalized_value,
                display_value=display_value,
                status=BuyerMemoryFactStatus.CONFIRMED,
                confidence_basis_points=10_000,
                source_message_id=source_message_id or prior.source_message_id,
                source_analysis_id=prior.source_analysis_id,
                supersedes_fact_id=prior.id,
                observed_at=now,
                confirmed_at=now,
                expires_at=None,
                created_at=now,
                updated_at=now,
                version=1,
            )
            persisted = await uow.buyer_memory_facts.save(corrected)
            await append_required_audit_event(
                uow.audit_events,
                buyer_memory_corrected_event(
                    tenant_id=context.tenant.id,
                    fact_id=persisted.id,
                    fact_type=prior.fact_type.value,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return persisted

    async def reject(
        self,
        *,
        context: TenantContext,
        fact_id: UUID,
        audit_context: AuditContext,
    ) -> BuyerMemoryFact:
        _require_mutate(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            fact = await uow.buyer_memory_facts.get(
                tenant_id=context.tenant.id,
                fact_id=fact_id,
            )
            if fact is None:
                raise BuyerMemoryServiceError("fact unavailable")
            await self._assert_thread_access(
                context=context,
                conversation_thread_id=fact.conversation_thread_id,
            )
            updated = replace(
                fact,
                status=BuyerMemoryFactStatus.REJECTED,
                updated_at=now,
                version=fact.version + 1,
            )
            persisted = await uow.buyer_memory_facts.save(updated)
            await uow.commit()
        return persisted

    async def soft_delete(
        self,
        *,
        context: TenantContext,
        fact_id: UUID,
        audit_context: AuditContext,
    ) -> BuyerMemoryFact:
        _require_mutate(context)
        now = self._clock.now()
        async with self._uow_factory() as uow:
            fact = await uow.buyer_memory_facts.get(
                tenant_id=context.tenant.id,
                fact_id=fact_id,
            )
            if fact is None:
                raise BuyerMemoryServiceError("fact unavailable")
            await self._assert_thread_access(
                context=context,
                conversation_thread_id=fact.conversation_thread_id,
            )
            updated = replace(
                fact,
                status=BuyerMemoryFactStatus.DELETED,
                updated_at=now,
                version=fact.version + 1,
            )
            persisted = await uow.buyer_memory_facts.save(updated)
            await append_required_audit_event(
                uow.audit_events,
                buyer_memory_deleted_event(
                    tenant_id=context.tenant.id,
                    fact_id=fact_id,
                    fact_type=fact.fact_type.value,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.USER,
                    actor_id=context.user.id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return persisted

    async def create_inferred(
        self,
        *,
        context: TenantContext,
        conversation_thread_id: UUID,
        lead_id: UUID | None,
        fact_type: BuyerMemoryFactType,
        normalized_value: str,
        display_value: str,
        confidence_basis_points: int,
        source_message_id: UUID | None,
        source_analysis_id: UUID | None,
    ) -> BuyerMemoryFact:
        """Internal helper for future extraction pipelines; not exposed via HTTP."""
        now = self._clock.now()
        fact = BuyerMemoryFact(
            id=self._uuid_factory(),
            tenant_id=context.tenant.id,
            conversation_thread_id=conversation_thread_id,
            lead_id=lead_id,
            fact_type=fact_type,
            normalized_value=normalized_value,
            display_value=display_value,
            status=BuyerMemoryFactStatus.INFERRED,
            confidence_basis_points=confidence_basis_points,
            source_message_id=source_message_id,
            source_analysis_id=source_analysis_id,
            supersedes_fact_id=None,
            observed_at=now,
            confirmed_at=None,
            expires_at=now + timedelta(seconds=DEFAULT_INFERENCE_TTL_SECONDS),
            created_at=now,
            updated_at=now,
            version=1,
        )
        async with self._uow_factory() as uow:
            persisted = await uow.buyer_memory_facts.save(fact)
            await uow.commit()
        return persisted

    async def _assert_thread_access(
        self,
        *,
        context: TenantContext,
        conversation_thread_id: UUID,
    ) -> None:
        if not _is_manager_only(context.membership.roles):
            return
        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise BuyerMemoryAccessDeniedError("access denied")
            statement = select(ManagerAssignmentRow.manager_user_id).where(
                ManagerAssignmentRow.tenant_id == context.tenant.id,
                ManagerAssignmentRow.conversation_thread_id == conversation_thread_id,
            )
            result = (await uow.session.execute(statement)).scalar_one_or_none()
            if result != context.user.id:
                raise BuyerMemoryAccessDeniedError("access denied")
