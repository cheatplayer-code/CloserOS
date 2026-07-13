"""Legal hold application service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.retention_persistence import LegalHoldNotFoundError
from closeros.domain.legal_hold import LegalHold, LegalHoldStatus

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]


class LegalHoldService:
    def __init__(self, *, uow_factory: _UnitOfWorkFactory, uuid_factory: _UuidFactory) -> None:
        self._uow_factory = uow_factory
        self._uuid_factory = uuid_factory

    async def create_hold(
        self,
        *,
        tenant_id: UUID,
        reason_code: str,
        reason_detail: str | None,
        created_by_user_id: UUID,
        created_at: datetime,
    ) -> LegalHold:
        uow = self._uow_factory()
        async with uow:
            existing = await uow.legal_holds.get_active_for_tenant(tenant_id=tenant_id)
            if existing is not None:
                return existing

            legal_hold = LegalHold(
                id=self._uuid_factory(),
                tenant_id=tenant_id,
                status=LegalHoldStatus.ACTIVE,
                reason_code=reason_code,
                reason_detail=reason_detail,
                created_by_user_id=created_by_user_id,
                released_by_user_id=None,
                created_at=created_at,
                released_at=None,
                updated_at=created_at,
            )
            await uow.legal_holds.add(legal_hold=legal_hold)
            await uow.commit()
            return legal_hold

    async def release_hold(
        self,
        *,
        tenant_id: UUID,
        legal_hold_id: UUID,
        released_by_user_id: UUID,
        released_at: datetime,
    ) -> LegalHold:
        uow = self._uow_factory()
        async with uow:
            existing = await uow.legal_holds.get_by_id(
                tenant_id=tenant_id,
                legal_hold_id=legal_hold_id,
            )
            if existing is None:
                raise LegalHoldNotFoundError("legal hold not found")
            if existing.status is LegalHoldStatus.RELEASED:
                return existing

            updated = replace(
                existing,
                status=LegalHoldStatus.RELEASED,
                released_by_user_id=released_by_user_id,
                released_at=released_at,
                updated_at=released_at,
            )
            await uow.legal_holds.update(legal_hold=updated)
            await uow.commit()
            return updated

    async def tenant_has_active_hold(self, *, tenant_id: UUID) -> bool:
        uow = self._uow_factory()
        async with uow:
            return await uow.legal_holds.tenant_has_active_hold(tenant_id=tenant_id)


__all__ = ["LegalHoldService"]
