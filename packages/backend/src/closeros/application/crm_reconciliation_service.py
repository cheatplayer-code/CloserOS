"""CRM reconciliation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from closeros.application.crm_sync_service import CrmSyncService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.crm_connection import CrmConnectionStatus
from closeros.infrastructure import crm_mappers

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


class CrmReconciliationService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        sync_service: CrmSyncService,
    ) -> None:
        self._uow_factory = uow_factory
        self._sync_service = sync_service

    async def reconcile_once(self, *, tenant_id: UUID) -> int:
        uow = self._uow_factory()
        async with uow:
            records = await uow.crm_connections.list_by_tenant(tenant_id=tenant_id)
        count = 0
        for record in records:
            connection = crm_mappers.connection_record_to_domain(record)
            if connection.status in {CrmConnectionStatus.ACTIVE, CrmConnectionStatus.DEGRADED}:
                await self._sync_service.sync_once(
                    tenant_id=tenant_id,
                    connection_id=connection.id,
                )
                count += 1
        return count


__all__ = ["CrmReconciliationService"]
