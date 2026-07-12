"""Bounded WhatsApp reconciliation service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.whatsapp_audit import whatsapp_reconciliation_completed_event
from closeros.domain.audit import AuditActorType

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_SENDING_STALE_AFTER = timedelta(minutes=10)
_RECONCILIATION_BATCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class WhatsAppReconciliationCounts:
    delivery_unknown_count: int
    stale_sending_count: int
    affected_count: int


class WhatsAppReconciliationService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        uuid_factory: _UuidFactory,
        clock: _Clock,
        service_actor_id: UUID,
    ) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory
        self._clock = clock
        self._service_actor_id = service_actor_id

    async def reconcile_once(
        self,
        *,
        tenant_id: UUID,
        audit_context: AuditContext,
    ) -> WhatsAppReconciliationCounts:
        now = self._clock()
        stale_before = now - _SENDING_STALE_AFTER

        uow = self._uow_factory()
        async with uow:
            delivery_unknown = await uow.outbound_messages.list_delivery_unknown(
                tenant_id=tenant_id,
                limit=_RECONCILIATION_BATCH_LIMIT,
            )
            stale_sending = await uow.outbound_messages.list_stale_sending(
                tenant_id=tenant_id,
                stale_before=stale_before,
                limit=_RECONCILIATION_BATCH_LIMIT,
            )

            affected_count = len(delivery_unknown) + len(stale_sending)
            await append_required_audit_event(
                uow.audit_events,
                whatsapp_reconciliation_completed_event(
                    tenant_id=tenant_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self._service_actor_id,
                    event_id=self._uuid_factory(),
                    affected_count=affected_count,
                ),
            )
            await uow.commit()

        return WhatsAppReconciliationCounts(
            delivery_unknown_count=len(delivery_unknown),
            stale_sending_count=len(stale_sending),
            affected_count=affected_count,
        )

    async def summarize_tenant(self, *, tenant_id: UUID) -> WhatsAppReconciliationCounts:
        now = self._clock()
        stale_before = now - _SENDING_STALE_AFTER
        uow = self._uow_factory()
        async with uow:
            delivery_unknown = await uow.outbound_messages.list_delivery_unknown(
                tenant_id=tenant_id,
                limit=_RECONCILIATION_BATCH_LIMIT,
            )
            stale_sending = await uow.outbound_messages.list_stale_sending(
                tenant_id=tenant_id,
                stale_before=stale_before,
                limit=_RECONCILIATION_BATCH_LIMIT,
            )
        return WhatsAppReconciliationCounts(
            delivery_unknown_count=len(delivery_unknown),
            stale_sending_count=len(stale_sending),
            affected_count=len(delivery_unknown) + len(stale_sending),
        )
