"""Mappers for CRM persistence records and ORM rows."""

from __future__ import annotations

from closeros.application.crm_persistence import (
    CrmConflictRecord,
    CrmConnectionRecord,
    CrmFieldMappingRecord,
    CrmSyncAttemptRecord,
    CrmSyncCheckpointRecord,
)
from closeros.domain.crm_conflict import CrmConflictResolution, CrmConflictStatus
from closeros.domain.crm_connection import CrmConnection, CrmConnectionStatus
from closeros.domain.crm_field_mapping import CrmFieldMappingStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.crm_sync import CrmSyncAttemptStatus, CrmSyncDirection
from closeros.infrastructure.crm_orm import (
    CrmConflictRow,
    CrmConnectionRow,
    CrmFieldMappingRow,
    CrmSyncAttemptRow,
    CrmSyncCheckpointRow,
)


def connection_record_to_domain(record: CrmConnectionRecord) -> CrmConnection:
    return CrmConnection(
        id=record.id,
        tenant_id=record.tenant_id,
        provider=record.provider,
        portal_domain=record.portal_domain,
        client_id_ref=record.client_id_ref,
        client_secret_ref=record.client_secret_ref,
        access_token_ref=record.access_token_ref,
        refresh_token_ref=record.refresh_token_ref,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_verified_at=record.last_verified_at,
        last_successful_sync_at=record.last_successful_sync_at,
        version=record.version,
    )


def connection_domain_to_record(connection: CrmConnection) -> CrmConnectionRecord:
    return CrmConnectionRecord(
        id=connection.id,
        tenant_id=connection.tenant_id,
        provider=connection.provider,
        portal_domain=connection.portal_domain,
        client_id_ref=connection.client_id_ref,
        client_secret_ref=connection.client_secret_ref,
        access_token_ref=connection.access_token_ref,
        refresh_token_ref=connection.refresh_token_ref,
        status=connection.status,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        last_verified_at=connection.last_verified_at,
        last_successful_sync_at=connection.last_successful_sync_at,
        version=connection.version,
    )


def connection_record_to_row(record: CrmConnectionRecord) -> CrmConnectionRow:
    return CrmConnectionRow(
        id=record.id,
        tenant_id=record.tenant_id,
        provider=record.provider.value,
        portal_domain=record.portal_domain,
        client_id_ref=record.client_id_ref,
        client_secret_ref=record.client_secret_ref,
        access_token_ref=record.access_token_ref,
        refresh_token_ref=record.refresh_token_ref,
        status=record.status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_verified_at=record.last_verified_at,
        last_successful_sync_at=record.last_successful_sync_at,
        version=record.version,
    )


def connection_row_to_record(row: CrmConnectionRow) -> CrmConnectionRecord:
    return CrmConnectionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        provider=CrmProviderCode(row.provider),
        portal_domain=row.portal_domain,
        client_id_ref=row.client_id_ref,
        client_secret_ref=row.client_secret_ref,
        access_token_ref=row.access_token_ref,
        refresh_token_ref=row.refresh_token_ref,
        status=CrmConnectionStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_verified_at=row.last_verified_at,
        last_successful_sync_at=row.last_successful_sync_at,
        version=row.version,
    )


def mapping_record_to_row(record: CrmFieldMappingRecord) -> CrmFieldMappingRow:
    return CrmFieldMappingRow(
        id=record.id,
        tenant_id=record.tenant_id,
        crm_connection_id=record.crm_connection_id,
        external_object_type=record.external_object_type,
        external_field_key=record.external_field_key,
        closeros_field=record.closeros_field,
        status=record.status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
        confirmed_by_user_id=record.confirmed_by_user_id,
        version=record.version,
    )


def mapping_row_to_record(row: CrmFieldMappingRow) -> CrmFieldMappingRecord:
    return CrmFieldMappingRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        crm_connection_id=row.crm_connection_id,
        external_object_type=row.external_object_type,
        external_field_key=row.external_field_key,
        closeros_field=row.closeros_field,
        status=CrmFieldMappingStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        confirmed_by_user_id=row.confirmed_by_user_id,
        version=row.version,
    )


def checkpoint_record_to_row(record: CrmSyncCheckpointRecord) -> CrmSyncCheckpointRow:
    return CrmSyncCheckpointRow(
        id=record.id,
        tenant_id=record.tenant_id,
        crm_connection_id=record.crm_connection_id,
        direction=record.direction.value,
        resource_type=record.resource_type,
        cursor=record.cursor,
        last_synced_at=record.last_synced_at,
        updated_at=record.updated_at,
        version=record.version,
    )


def checkpoint_row_to_record(row: CrmSyncCheckpointRow) -> CrmSyncCheckpointRecord:
    return CrmSyncCheckpointRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        crm_connection_id=row.crm_connection_id,
        direction=CrmSyncDirection(row.direction),
        resource_type=row.resource_type,
        cursor=row.cursor,
        last_synced_at=row.last_synced_at,
        updated_at=row.updated_at,
        version=row.version,
    )


def attempt_record_to_row(record: CrmSyncAttemptRecord) -> CrmSyncAttemptRow:
    return CrmSyncAttemptRow(
        id=record.id,
        tenant_id=record.tenant_id,
        crm_connection_id=record.crm_connection_id,
        direction=record.direction.value,
        status=record.status.value,
        resource_type=record.resource_type,
        started_at=record.started_at,
        finished_at=record.finished_at,
        records_seen=record.records_seen,
        records_changed=record.records_changed,
        error_code=record.error_code,
    )


def attempt_row_to_record(row: CrmSyncAttemptRow) -> CrmSyncAttemptRecord:
    return CrmSyncAttemptRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        crm_connection_id=row.crm_connection_id,
        direction=CrmSyncDirection(row.direction),
        status=CrmSyncAttemptStatus(row.status),
        resource_type=row.resource_type,
        started_at=row.started_at,
        finished_at=row.finished_at,
        records_seen=row.records_seen,
        records_changed=row.records_changed,
        error_code=row.error_code,
    )


def conflict_record_to_row(record: CrmConflictRecord) -> CrmConflictRow:
    return CrmConflictRow(
        id=record.id,
        tenant_id=record.tenant_id,
        crm_connection_id=record.crm_connection_id,
        external_object_type=record.external_object_type,
        external_object_id=record.external_object_id,
        field_key=record.field_key,
        crm_value_hash=record.crm_value_hash,
        closeros_value_hash=record.closeros_value_hash,
        status=record.status.value,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
        resolved_by_user_id=record.resolved_by_user_id,
        resolution=None if record.resolution is None else record.resolution.value,
        version=record.version,
    )


def conflict_row_to_record(row: CrmConflictRow) -> CrmConflictRecord:
    return CrmConflictRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        crm_connection_id=row.crm_connection_id,
        external_object_type=row.external_object_type,
        external_object_id=row.external_object_id,
        field_key=row.field_key,
        crm_value_hash=row.crm_value_hash,
        closeros_value_hash=row.closeros_value_hash,
        status=CrmConflictStatus(row.status),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
        resolution=None if row.resolution is None else CrmConflictResolution(row.resolution),
        version=row.version,
    )
