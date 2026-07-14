"""SQLAlchemy repositories for synthetic seed provenance."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.domain.synthetic_seed import (
    SyntheticSeedManifest,
    SyntheticSeedResetState,
    SyntheticSeedResource,
    SyntheticSeedResourceType,
)
from closeros.infrastructure.synthetic_seed_orm import (
    SyntheticSeedManifestRow,
    SyntheticSeedResourceRow,
)


def _manifest_from_row(row: SyntheticSeedManifestRow) -> SyntheticSeedManifest:
    return SyntheticSeedManifest(
        id=row.id,
        tenant_id=row.tenant_id,
        seed_version=row.seed_version,
        seed_run_id=row.seed_run_id,
        created_at=row.created_at,
        reset_state=SyntheticSeedResetState(row.reset_state),
    )


def _resource_from_row(row: SyntheticSeedResourceRow) -> SyntheticSeedResource:
    return SyntheticSeedResource(
        id=row.id,
        tenant_id=row.tenant_id,
        manifest_id=row.manifest_id,
        resource_type=SyntheticSeedResourceType(row.resource_type),
        resource_id=row.resource_id,
        deletion_order=row.deletion_order,
    )


class SqlAlchemySyntheticSeedManifestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, manifest: SyntheticSeedManifest) -> None:
        self._session.add(
            SyntheticSeedManifestRow(
                id=manifest.id,
                tenant_id=manifest.tenant_id,
                seed_version=manifest.seed_version,
                seed_run_id=manifest.seed_run_id,
                created_at=manifest.created_at,
                reset_state=manifest.reset_state.value,
            )
        )
        await self._session.flush()

    async def get_active_for_tenant(
        self,
        *,
        tenant_id: UUID,
        seed_version: str,
    ) -> SyntheticSeedManifest | None:
        statement = select(SyntheticSeedManifestRow).where(
            SyntheticSeedManifestRow.tenant_id == tenant_id,
            SyntheticSeedManifestRow.seed_version == seed_version,
            SyntheticSeedManifestRow.reset_state == SyntheticSeedResetState.ACTIVE.value,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else _manifest_from_row(row)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> SyntheticSeedManifest | None:
        statement = select(SyntheticSeedManifestRow).where(
            SyntheticSeedManifestRow.tenant_id == tenant_id,
            SyntheticSeedManifestRow.id == manifest_id,
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else _manifest_from_row(row)

    async def mark_reset_state(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
        reset_state: SyntheticSeedResetState,
        expected_state: SyntheticSeedResetState,
    ) -> SyntheticSeedManifest | None:
        statement = (
            update(SyntheticSeedManifestRow)
            .where(
                SyntheticSeedManifestRow.tenant_id == tenant_id,
                SyntheticSeedManifestRow.id == manifest_id,
                SyntheticSeedManifestRow.reset_state == expected_state.value,
            )
            .values(reset_state=reset_state.value)
            .returning(SyntheticSeedManifestRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else _manifest_from_row(row)


class SqlAlchemySyntheticSeedResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, *, resources: tuple[SyntheticSeedResource, ...]) -> None:
        for resource in resources:
            self._session.add(
                SyntheticSeedResourceRow(
                    id=resource.id,
                    tenant_id=resource.tenant_id,
                    manifest_id=resource.manifest_id,
                    resource_type=resource.resource_type.value,
                    resource_id=resource.resource_id,
                    deletion_order=resource.deletion_order,
                )
            )
        await self._session.flush()

    async def list_for_manifest(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> tuple[SyntheticSeedResource, ...]:
        statement = (
            select(SyntheticSeedResourceRow)
            .where(
                SyntheticSeedResourceRow.tenant_id == tenant_id,
                SyntheticSeedResourceRow.manifest_id == manifest_id,
            )
            .order_by(
                SyntheticSeedResourceRow.deletion_order.desc(),
                SyntheticSeedResourceRow.resource_type.asc(),
                SyntheticSeedResourceRow.resource_id.asc(),
            )
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(_resource_from_row(row) for row in rows)

    async def delete_for_manifest(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> int:
        statement = delete(SyntheticSeedResourceRow).where(
            SyntheticSeedResourceRow.tenant_id == tenant_id,
            SyntheticSeedResourceRow.manifest_id == manifest_id,
        )
        result = await self._session.execute(statement)
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)
