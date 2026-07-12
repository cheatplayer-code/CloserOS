"""Shared repository helpers for tenant-scoped persistence access."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.persistence_errors import TenantMismatchError


class _TenantScopedRow(Protocol):
    tenant_id: UUID


async def tenant_scoped_get[RowT: _TenantScopedRow](
    session: AsyncSession,
    model: type[RowT],
    *,
    tenant_id: UUID,
    record_id: UUID,
) -> RowT | None:
    row = await session.get(model, record_id)
    if row is None:
        return None
    if row.tenant_id != tenant_id:
        raise TenantMismatchError("tenant scope mismatch")
    return row


async def tenant_scoped_get_required[RowT: _TenantScopedRow](
    session: AsyncSession,
    model: type[RowT],
    *,
    tenant_id: UUID,
    record_id: UUID,
    not_found_error: type[Exception],
    not_found_message: str,
) -> RowT:
    row = await tenant_scoped_get(
        session,
        model,
        tenant_id=tenant_id,
        record_id=record_id,
    )
    if row is None:
        raise not_found_error(not_found_message)
    return row
