"""PostgreSQL repositories for CRM integrations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.crm_persistence import (
    CrmConflictRecord,
    CrmConnectionNotFoundError,
    CrmConnectionRecord,
    CrmFieldMappingRecord,
    CrmPersistenceError,
    CrmSyncAttemptRecord,
    CrmSyncCheckpointRecord,
    CrmVersionConflictError,
    DuplicateCrmConnectionError,
)
from closeros.domain.crm_conflict import CrmConflictStatus
from closeros.domain.crm_sync import CrmSyncDirection
from closeros.infrastructure import crm_mappers as mappers
from closeros.infrastructure.crm_orm import (
    CrmConflictRow,
    CrmConnectionRow,
    CrmFieldMappingRow,
    CrmSyncAttemptRow,
    CrmSyncCheckpointRow,
)
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise translate_integrity_error(
            error,
            constraint_errors={
                "uq_crm_connections_tenant_id_provider_portal_domain": DuplicateCrmConnectionError,
            },
            default=CrmPersistenceError,
            message="crm persistence integrity error",
        ) from error


class SqlAlchemyCrmConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: CrmConnectionRecord) -> None:
        self._session.add(mappers.connection_record_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self, *, tenant_id: UUID, connection_id: UUID
    ) -> CrmConnectionRecord | None:
        row = await tenant_scoped_get(
            self._session,
            CrmConnectionRow,
            tenant_id=tenant_id,
            record_id=connection_id,
        )
        return None if row is None else mappers.connection_row_to_record(row)

    async def get_by_id_for_update(
        self, *, tenant_id: UUID, connection_id: UUID
    ) -> CrmConnectionRecord | None:
        statement = (
            select(CrmConnectionRow)
            .where(CrmConnectionRow.tenant_id == tenant_id, CrmConnectionRow.id == connection_id)
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.connection_row_to_record(row)

    async def list_by_tenant(self, *, tenant_id: UUID) -> tuple[CrmConnectionRecord, ...]:
        statement = (
            select(CrmConnectionRow)
            .where(CrmConnectionRow.tenant_id == tenant_id)
            .order_by(CrmConnectionRow.created_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.connection_row_to_record(row) for row in rows)

    async def update(
        self, *, record: CrmConnectionRecord, expected_version: int
    ) -> CrmConnectionRecord:
        row = (
            await self._session.execute(
                select(CrmConnectionRow)
                .where(
                    CrmConnectionRow.tenant_id == record.tenant_id, CrmConnectionRow.id == record.id
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise CrmConnectionNotFoundError("crm connection not found")
        if row.version != expected_version:
            raise CrmVersionConflictError("crm connection version conflict")
        row.provider = record.provider.value
        row.portal_domain = record.portal_domain
        row.client_id_ref = record.client_id_ref
        row.client_secret_ref = record.client_secret_ref
        row.access_token_ref = record.access_token_ref
        row.refresh_token_ref = record.refresh_token_ref
        row.status = record.status.value
        row.updated_at = record.updated_at
        row.last_verified_at = record.last_verified_at
        row.last_successful_sync_at = record.last_successful_sync_at
        row.version = record.version
        await _flush(self._session)
        return mappers.connection_row_to_record(row)


class SqlAlchemyCrmFieldMappingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, *, record: CrmFieldMappingRecord) -> CrmFieldMappingRecord:
        existing = (
            await self._session.execute(
                select(CrmFieldMappingRow).where(
                    CrmFieldMappingRow.tenant_id == record.tenant_id,
                    CrmFieldMappingRow.crm_connection_id == record.crm_connection_id,
                    CrmFieldMappingRow.external_object_type == record.external_object_type,
                    CrmFieldMappingRow.external_field_key == record.external_field_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(mappers.mapping_record_to_row(record))
            await _flush(self._session)
            return record
        existing.closeros_field = record.closeros_field
        existing.status = record.status.value
        existing.updated_at = record.updated_at
        existing.confirmed_by_user_id = record.confirmed_by_user_id
        existing.version = existing.version + 1
        await _flush(self._session)
        return mappers.mapping_row_to_record(existing)

    async def list_by_connection(
        self, *, tenant_id: UUID, crm_connection_id: UUID
    ) -> tuple[CrmFieldMappingRecord, ...]:
        statement = select(CrmFieldMappingRow).where(
            CrmFieldMappingRow.tenant_id == tenant_id,
            CrmFieldMappingRow.crm_connection_id == crm_connection_id,
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.mapping_row_to_record(row) for row in rows)


class SqlAlchemyCrmSyncCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        direction: CrmSyncDirection,
        resource_type: str,
    ) -> CrmSyncCheckpointRecord | None:
        row = (
            await self._session.execute(
                select(CrmSyncCheckpointRow).where(
                    CrmSyncCheckpointRow.tenant_id == tenant_id,
                    CrmSyncCheckpointRow.crm_connection_id == crm_connection_id,
                    CrmSyncCheckpointRow.direction == direction.value,
                    CrmSyncCheckpointRow.resource_type == resource_type,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.checkpoint_row_to_record(row)

    async def upsert(self, *, record: CrmSyncCheckpointRecord) -> CrmSyncCheckpointRecord:
        existing = await self.get(
            tenant_id=record.tenant_id,
            crm_connection_id=record.crm_connection_id,
            direction=record.direction,
            resource_type=record.resource_type,
        )
        if existing is None:
            self._session.add(mappers.checkpoint_record_to_row(record))
            await _flush(self._session)
            return record
        row = (
            await self._session.execute(
                select(CrmSyncCheckpointRow).where(CrmSyncCheckpointRow.id == existing.id)
            )
        ).scalar_one()
        row.cursor = record.cursor
        row.last_synced_at = record.last_synced_at
        row.updated_at = record.updated_at
        row.version = existing.version + 1
        await _flush(self._session)
        return mappers.checkpoint_row_to_record(row)


class SqlAlchemyCrmSyncAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, *, record: CrmSyncAttemptRecord) -> None:
        self._session.add(mappers.attempt_record_to_row(record))
        await _flush(self._session)

    async def list_recent(
        self, *, tenant_id: UUID, crm_connection_id: UUID, limit: int
    ) -> tuple[CrmSyncAttemptRecord, ...]:
        statement = (
            select(CrmSyncAttemptRow)
            .where(
                CrmSyncAttemptRow.tenant_id == tenant_id,
                CrmSyncAttemptRow.crm_connection_id == crm_connection_id,
            )
            .order_by(CrmSyncAttemptRow.started_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.attempt_row_to_record(row) for row in rows)


class SqlAlchemyCrmConflictRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: CrmConflictRecord) -> None:
        self._session.add(mappers.conflict_record_to_row(record))
        await _flush(self._session)

    async def list_open(
        self, *, tenant_id: UUID, crm_connection_id: UUID
    ) -> tuple[CrmConflictRecord, ...]:
        statement = select(CrmConflictRow).where(
            CrmConflictRow.tenant_id == tenant_id,
            CrmConflictRow.crm_connection_id == crm_connection_id,
            CrmConflictRow.status == CrmConflictStatus.OPEN.value,
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.conflict_row_to_record(row) for row in rows)

    async def get_by_id_for_update(
        self, *, tenant_id: UUID, conflict_id: UUID
    ) -> CrmConflictRecord | None:
        statement = (
            select(CrmConflictRow)
            .where(CrmConflictRow.tenant_id == tenant_id, CrmConflictRow.id == conflict_id)
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.conflict_row_to_record(row)

    async def update(
        self, *, record: CrmConflictRecord, expected_version: int
    ) -> CrmConflictRecord:
        row = (
            await self._session.execute(
                select(CrmConflictRow)
                .where(CrmConflictRow.tenant_id == record.tenant_id, CrmConflictRow.id == record.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise CrmConnectionNotFoundError("crm conflict not found")
        if row.version != expected_version:
            raise CrmVersionConflictError("crm conflict version conflict")
        row.status = record.status.value
        row.resolved_at = record.resolved_at
        row.resolved_by_user_id = record.resolved_by_user_id
        row.resolution = None if record.resolution is None else record.resolution.value
        row.version = record.version
        await _flush(self._session)
        return mappers.conflict_row_to_record(row)
