"""CRM synchronization application service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.crm_persistence import (
    CrmConflictRecord,
    CrmSyncAttemptRecord,
    CrmSyncCheckpointRecord,
)
from closeros.application.crm_ports import (
    CrmAdapter,
    CrmAdapterError,
    CrmContactSnapshot,
    CrmContactWrite,
    CrmCredentialResolver,
    CrmDealSnapshot,
    CrmDealWrite,
    crm_field_value_hash,
    crm_snapshot_field_value,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.crm_conflict import CrmConflictResolution, CrmConflictStatus
from closeros.domain.crm_connection import CrmConnection, CrmConnectionStatus
from closeros.domain.crm_field_mapping import CrmFieldMappingStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.crm_sync import CrmSyncAttemptStatus, CrmSyncDirection
from closeros.infrastructure import crm_mappers

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_INBOUND_RESOURCE_TYPES = ("deal", "contact")


class CrmSyncServiceError(Exception):
    """Raised when CRM synchronization cannot proceed."""


class CrmSyncService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        credential_resolver: CrmCredentialResolver,
        adapters: dict[CrmProviderCode, CrmAdapter],
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._credential_resolver = credential_resolver
        self._adapters = adapters
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def sync_once(self, *, tenant_id: UUID, connection_id: UUID) -> None:
        await self.sync_inbound_once(tenant_id=tenant_id, connection_id=connection_id)
        await self.sync_outbound_once(tenant_id=tenant_id, connection_id=connection_id)

    async def sync_inbound_once(self, *, tenant_id: UUID, connection_id: UUID) -> None:
        connection, adapter, access_token = await self._resolve_sync_context(
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        started_at = self._clock()
        records_seen = 0
        records_changed = 0
        try:
            for resource_type in _INBOUND_RESOURCE_TYPES:
                seen, changed = await self._sync_inbound_resource(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    connection=connection,
                    adapter=adapter,
                    access_token=access_token,
                    resource_type=resource_type,
                )
                records_seen += seen
                records_changed += changed
        except CrmAdapterError as error:
            await self._append_attempt(
                tenant_id=tenant_id,
                connection_id=connection_id,
                direction=CrmSyncDirection.INBOUND,
                started_at=started_at,
                status=CrmSyncAttemptStatus.FAILED,
                records_seen=records_seen,
                records_changed=records_changed,
                error_code="adapter_failed",
            )
            raise CrmSyncServiceError("crm adapter failed") from error

        now = self._clock()
        await self._finalize_successful_sync(
            tenant_id=tenant_id,
            connection_id=connection_id,
            connection=connection,
            direction=CrmSyncDirection.INBOUND,
            started_at=started_at,
            finished_at=now,
            records_seen=records_seen,
            records_changed=records_changed,
        )

    async def sync_outbound_once(self, *, tenant_id: UUID, connection_id: UUID) -> None:
        started_at = self._clock()
        connection, adapter, access_token = await self._resolve_sync_context(
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        records_changed = 0
        records_seen = 0
        try:
            uow = self._uow_factory()
            async with uow:
                conflicts = await uow.crm_conflicts.list_open(
                    tenant_id=tenant_id,
                    crm_connection_id=connection_id,
                )
            records_seen = len(conflicts)
            for conflict in conflicts:
                if conflict.resolution != CrmConflictResolution.USE_CLOSEROS:
                    continue
                closeros_value = conflict.closeros_value_hash
                if conflict.external_object_type == "deal":
                    await adapter.update_deal(
                        connection=connection,
                        access_token=access_token,
                        external_deal_id=conflict.external_object_id,
                        fields=_deal_fields_for_mapping(
                            conflict.field_key,
                            closeros_value,
                        ),
                    )
                    records_changed += 1
                elif conflict.external_object_type == "contact":
                    await adapter.update_contact(
                        connection=connection,
                        access_token=access_token,
                        external_contact_id=conflict.external_object_id,
                        fields=_contact_fields_for_mapping(
                            conflict.field_key,
                            closeros_value,
                        ),
                    )
                    records_changed += 1
        except CrmAdapterError as error:
            await self._append_attempt(
                tenant_id=tenant_id,
                connection_id=connection_id,
                direction=CrmSyncDirection.OUTBOUND,
                started_at=started_at,
                status=CrmSyncAttemptStatus.FAILED,
                records_seen=records_seen,
                records_changed=records_changed,
                error_code="adapter_failed",
                resource_type="field",
            )
            raise CrmSyncServiceError("crm adapter failed") from error

        now = self._clock()
        await self._append_attempt(
            tenant_id=tenant_id,
            connection_id=connection_id,
            direction=CrmSyncDirection.OUTBOUND,
            started_at=started_at,
            status=CrmSyncAttemptStatus.SUCCEEDED,
            records_seen=records_seen,
            records_changed=records_changed,
            error_code=None,
            resource_type="field",
            finished_at=now,
        )

    async def recent_attempts(
        self, *, tenant_id: UUID, connection_id: UUID, limit: int = 10
    ) -> tuple[CrmSyncAttemptRecord, ...]:
        uow = self._uow_factory()
        async with uow:
            return await uow.crm_sync_attempts.list_recent(
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
                limit=limit,
            )

    async def list_open_conflicts(
        self, *, tenant_id: UUID, connection_id: UUID
    ) -> tuple[CrmConflictRecord, ...]:
        uow = self._uow_factory()
        async with uow:
            return await uow.crm_conflicts.list_open(
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
            )

    async def _resolve_sync_context(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> tuple[CrmConnection, CrmAdapter, str]:
        uow = self._uow_factory()
        async with uow:
            record = await uow.crm_connections.get_by_id(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if record is None:
                raise CrmSyncServiceError("crm connection unavailable")
            connection = crm_mappers.connection_record_to_domain(record)
            if connection.status not in {CrmConnectionStatus.ACTIVE, CrmConnectionStatus.DEGRADED}:
                raise CrmSyncServiceError("crm connection not syncable")
        if connection.access_token_ref is None:
            raise CrmSyncServiceError("crm credentials unavailable")
        secret = await self._credential_resolver.resolve_access_token(
            tenant_id=tenant_id,
            crm_connection_id=connection_id,
            reference_key=connection.access_token_ref,
        )
        adapter = self._adapters.get(connection.provider)
        if secret is None or adapter is None:
            raise CrmSyncServiceError("crm adapter unavailable")
        return connection, adapter, secret.value.decode("utf-8")

    async def _sync_inbound_resource(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        connection: CrmConnection,
        adapter: CrmAdapter,
        access_token: str,
        resource_type: str,
    ) -> tuple[int, int]:
        uow = self._uow_factory()
        async with uow:
            checkpoint = await uow.crm_sync_checkpoints.get(
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
                direction=CrmSyncDirection.INBOUND,
                resource_type=resource_type,
            )
            mappings = await uow.crm_field_mappings.list_by_connection(
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
            )
            open_conflicts = await uow.crm_conflicts.list_open(
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
            )
        updated_since = None if checkpoint is None else checkpoint.last_synced_at
        cursor = None if checkpoint is None else checkpoint.cursor
        snapshots: tuple[CrmDealSnapshot, ...] | tuple[CrmContactSnapshot, ...]
        if resource_type == "deal":
            deal_page = await adapter.list_deals(
                connection=connection,
                access_token=access_token,
                cursor=cursor,
                updated_since=updated_since,
            )
            snapshots = deal_page.deals
            next_cursor = deal_page.next_cursor
        else:
            contact_page = await adapter.list_contacts(
                connection=connection,
                access_token=access_token,
                cursor=cursor,
                updated_since=updated_since,
            )
            snapshots = contact_page.contacts
            next_cursor = contact_page.next_cursor

        now = self._clock()
        conflicts_created = 0
        uow = self._uow_factory()
        async with uow:
            active_mappings = [
                mapping
                for mapping in mappings
                if mapping.status == CrmFieldMappingStatus.ACTIVE
                and mapping.external_object_type == resource_type
            ]
            for snapshot in snapshots:
                external_object_id = _external_object_id(snapshot)
                for mapping in active_mappings:
                    crm_value = crm_snapshot_field_value(
                        snapshot,
                        external_field_key=mapping.external_field_key,
                    )
                    crm_hash = crm_field_value_hash(crm_value)
                    existing = _find_open_conflict(
                        open_conflicts,
                        external_object_id=external_object_id,
                        field_key=mapping.external_field_key,
                    )
                    if existing is None:
                        continue
                    if existing.closeros_value_hash == crm_hash:
                        continue
                    if existing.crm_value_hash != crm_hash:
                        updated = replace(
                            existing,
                            crm_value_hash=crm_hash,
                            version=existing.version + 1,
                        )
                        await uow.crm_conflicts.update(
                            record=updated,
                            expected_version=existing.version,
                        )
                        conflicts_created += 1
            checkpoint_record = CrmSyncCheckpointRecord(
                id=self._uuid_factory() if checkpoint is None else checkpoint.id,
                tenant_id=tenant_id,
                crm_connection_id=connection_id,
                direction=CrmSyncDirection.INBOUND,
                resource_type=resource_type,
                cursor=next_cursor,
                last_synced_at=now,
                updated_at=now,
                version=1 if checkpoint is None else checkpoint.version + 1,
            )
            await uow.crm_sync_checkpoints.upsert(record=checkpoint_record)
            await uow.commit()
        return len(snapshots), len(snapshots) + conflicts_created

    async def _finalize_successful_sync(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        connection: CrmConnection,
        direction: CrmSyncDirection,
        started_at: datetime,
        finished_at: datetime,
        records_seen: int,
        records_changed: int,
    ) -> None:
        await self._append_attempt(
            tenant_id=tenant_id,
            connection_id=connection_id,
            direction=direction,
            started_at=started_at,
            status=CrmSyncAttemptStatus.SUCCEEDED,
            records_seen=records_seen,
            records_changed=records_changed,
            error_code=None,
            resource_type="aggregate",
            finished_at=finished_at,
        )
        uow = self._uow_factory()
        async with uow:
            updated_connection = replace(
                connection,
                last_successful_sync_at=finished_at,
                updated_at=finished_at,
                version=connection.version + 1,
            )
            await uow.crm_connections.update(
                record=crm_mappers.connection_domain_to_record(updated_connection),
                expected_version=connection.version,
            )
            await uow.commit()

    async def _append_attempt(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        direction: CrmSyncDirection,
        started_at: datetime,
        status: CrmSyncAttemptStatus,
        records_seen: int,
        records_changed: int,
        error_code: str | None,
        resource_type: str = "deal",
        finished_at: datetime | None = None,
    ) -> None:
        now = finished_at or self._clock()
        uow = self._uow_factory()
        async with uow:
            await uow.crm_sync_attempts.append(
                record=CrmSyncAttemptRecord(
                    id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    crm_connection_id=connection_id,
                    direction=direction,
                    status=status,
                    resource_type=resource_type,
                    started_at=started_at,
                    finished_at=now,
                    records_seen=records_seen,
                    records_changed=records_changed,
                    error_code=error_code,
                )
            )
            await uow.commit()


def _external_object_id(snapshot: CrmDealSnapshot | CrmContactSnapshot) -> str:
    if isinstance(snapshot, CrmDealSnapshot):
        return snapshot.external_deal_id
    return snapshot.external_contact_id


def _find_open_conflict(
    conflicts: tuple[CrmConflictRecord, ...],
    *,
    external_object_id: str,
    field_key: str,
) -> CrmConflictRecord | None:
    for conflict in conflicts:
        if (
            conflict.external_object_id == external_object_id
            and conflict.field_key == field_key
            and conflict.status == CrmConflictStatus.OPEN
        ):
            return conflict
    return None


def _deal_fields_for_mapping(field_key: str, value: str) -> CrmDealWrite:
    if field_key == "TITLE":
        return CrmDealWrite(title=value)
    if field_key == "STAGE_ID":
        return CrmDealWrite(stage=value)
    if field_key == "ASSIGNED_BY_ID":
        return CrmDealWrite(owner_external_id=value)
    if field_key == "CURRENCY_ID":
        return CrmDealWrite(currency=value)
    if field_key == "CONTACT_ID":
        return CrmDealWrite(contact_external_id=value)
    return CrmDealWrite()


def _contact_fields_for_mapping(field_key: str, value: str) -> CrmContactWrite:
    if field_key == "NAME":
        return CrmContactWrite(first_name=value)
    if field_key == "LAST_NAME":
        return CrmContactWrite(last_name=value)
    if field_key == "EMAIL":
        return CrmContactWrite(email=value)
    if field_key == "PHONE":
        return CrmContactWrite(phone=value)
    if field_key == "ASSIGNED_BY_ID":
        return CrmContactWrite(owner_external_id=value)
    return CrmContactWrite()
