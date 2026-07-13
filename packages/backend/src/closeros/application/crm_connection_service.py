"""Application service for CRM connection lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.crm_audit import crm_connection_event
from closeros.application.crm_persistence import (
    CrmConnectionNotFoundError,
    CrmVersionConflictError,
)
from closeros.application.crm_ports import (
    CrmAdapter,
    CrmAdapterError,
    CrmCredentialResolver,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.audit import AuditAction, AuditActorType
from closeros.domain.crm_connection import CrmConnection, CrmConnectionStatus
from closeros.domain.crm_provider import CrmProviderCode
from closeros.infrastructure import crm_mappers

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]


class CrmConnectionServiceError(Exception):
    """Raised when CRM connection operations cannot be completed."""


class CrmConnectionService:
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

    async def create_connection(
        self,
        *,
        tenant_id: UUID,
        provider: CrmProviderCode,
        portal_domain: str | None,
        client_id_ref: str | None,
        client_secret_ref: str | None,
        access_token_ref: str | None,
        refresh_token_ref: str | None,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> CrmConnection:
        now = self._clock()
        connection = CrmConnection(
            id=self._uuid_factory(),
            tenant_id=tenant_id,
            provider=provider,
            portal_domain=portal_domain,
            client_id_ref=client_id_ref,
            client_secret_ref=client_secret_ref,
            access_token_ref=access_token_ref,
            refresh_token_ref=refresh_token_ref,
            status=CrmConnectionStatus.DRAFT,
            created_at=now,
            updated_at=now,
            last_verified_at=None,
            last_successful_sync_at=None,
            version=1,
        )
        uow = self._uow_factory()
        async with uow:
            await uow.crm_connections.add(
                record=crm_mappers.connection_domain_to_record(connection)
            )
            await append_required_audit_event(
                uow.audit_events,
                crm_connection_event(
                    action=AuditAction.CRM_CONNECTION_CREATED,
                    tenant_id=tenant_id,
                    connection_id=connection.id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return connection

    async def list_connections(self, *, tenant_id: UUID) -> tuple[CrmConnection, ...]:
        uow = self._uow_factory()
        async with uow:
            records = await uow.crm_connections.list_by_tenant(tenant_id=tenant_id)
        return tuple(crm_mappers.connection_record_to_domain(record) for record in records)

    async def update_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        portal_domain: str | None,
        client_id_ref: str | None,
        client_secret_ref: str | None,
        access_token_ref: str | None,
        refresh_token_ref: str | None,
        expected_version: int,
    ) -> CrmConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.crm_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise CrmConnectionNotFoundError("crm connection not found")
            domain = crm_mappers.connection_record_to_domain(current)
            updated = replace(
                domain,
                portal_domain=portal_domain,
                client_id_ref=client_id_ref,
                client_secret_ref=client_secret_ref,
                access_token_ref=access_token_ref,
                refresh_token_ref=refresh_token_ref,
                updated_at=now,
                version=domain.version + 1,
            )
            try:
                persisted = await uow.crm_connections.update(
                    record=crm_mappers.connection_domain_to_record(updated),
                    expected_version=expected_version,
                )
            except CrmVersionConflictError as error:
                raise CrmConnectionServiceError("operation unavailable") from error
            await uow.commit()
        return crm_mappers.connection_record_to_domain(persisted)

    async def verify_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> CrmConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.crm_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise CrmConnectionNotFoundError("crm connection not found")
            domain = crm_mappers.connection_record_to_domain(current)
            access_token = await self._resolve_access_token(domain)
            adapter = self._adapters.get(domain.provider)
            if access_token is None or adapter is None:
                raise CrmConnectionServiceError("credentials unavailable")
            try:
                verified = await adapter.verify_connection(
                    connection=domain,
                    access_token=access_token,
                )
            except CrmAdapterError as error:
                raise CrmConnectionServiceError("verification failed") from error
            updated = replace(
                domain,
                status=CrmConnectionStatus.ACTIVE if verified else CrmConnectionStatus.DEGRADED,
                last_verified_at=now,
                updated_at=now,
                version=domain.version + 1,
            )
            persisted = await uow.crm_connections.update(
                record=crm_mappers.connection_domain_to_record(updated),
                expected_version=expected_version,
            )
            await append_required_audit_event(
                uow.audit_events,
                crm_connection_event(
                    action=AuditAction.CRM_CONNECTION_VERIFIED,
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    outcome="verified" if verified else "degraded",
                ),
            )
            await uow.commit()
        return crm_mappers.connection_record_to_domain(persisted)

    async def disable_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> CrmConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.crm_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise CrmConnectionNotFoundError("crm connection not found")
            domain = crm_mappers.connection_record_to_domain(current)
            updated = replace(
                domain,
                status=CrmConnectionStatus.DISABLED,
                updated_at=now,
                version=domain.version + 1,
            )
            persisted = await uow.crm_connections.update(
                record=crm_mappers.connection_domain_to_record(updated),
                expected_version=expected_version,
            )
            await append_required_audit_event(
                uow.audit_events,
                crm_connection_event(
                    action=AuditAction.CRM_CONNECTION_DISABLED,
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                ),
            )
            await uow.commit()
        return crm_mappers.connection_record_to_domain(persisted)

    async def _resolve_access_token(self, connection: CrmConnection) -> str | None:
        if connection.access_token_ref is None:
            return None
        secret = await self._credential_resolver.resolve_access_token(
            tenant_id=connection.tenant_id,
            crm_connection_id=connection.id,
            reference_key=connection.access_token_ref,
        )
        return None if secret is None else secret.value.decode("utf-8")
