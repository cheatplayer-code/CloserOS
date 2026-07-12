"""Outbox handler for provider template synchronization jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.provider_ports import WhatsAppCredentialResolver
from closeros.application.provider_template_persistence import ProviderMessageTemplateRecord
from closeros.application.whatsapp_audit import (
    provider_templates_sync_completed_event,
    provider_templates_sync_failed_event,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.domain.provider_template import ProviderTemplateApprovalStatus
from closeros.infrastructure import whatsapp_mappers
from closeros.infrastructure.whatsapp_cloud_api_client import (
    WhatsAppCloudApiClientError,
    build_client_for_connection,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_APPROVAL_STATUS_MAP = {
    "approved": ProviderTemplateApprovalStatus.APPROVED,
    "pending": ProviderTemplateApprovalStatus.PENDING,
    "rejected": ProviderTemplateApprovalStatus.REJECTED,
    "paused": ProviderTemplateApprovalStatus.PAUSED,
    "disabled": ProviderTemplateApprovalStatus.DISABLED,
}


class ProviderTemplatesSyncHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("provider templates sync failed")


@dataclass(frozen=True, slots=True)
class ProviderTemplatesSyncHandler:
    uow_factory: _UnitOfWorkFactory
    credential_resolver: WhatsAppCredentialResolver
    service_actor_id: UUID
    uuid_factory: _UuidFactory
    clock: _Clock

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None:
            raise ProviderTemplatesSyncHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )

        tenant_id = job.tenant_id
        connection_id = job.reference.resource_id
        occurred_at = job.processing_started_at or job.created_at
        audit_context = AuditContext(correlation_id=job.id)

        uow = self.uow_factory()
        async with uow:
            record = await uow.whatsapp_cloud_connections.get_by_id(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if record is None:
                raise ProviderTemplatesSyncHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            connection = whatsapp_mappers.record_to_domain(record)
            if connection.access_token_ref is None:
                raise ProviderTemplatesSyncHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )
            secret = await self.credential_resolver.resolve_access_token(
                tenant_id=tenant_id,
                whatsapp_connection_id=connection.id,
                reference_key=connection.access_token_ref,
            )
            if secret is None:
                raise ProviderTemplatesSyncHandlerError(
                    error_code=OutboxErrorCode.RESOURCE_UNAVAILABLE,
                    permanent=True,
                )

        client = build_client_for_connection(
            graph_api_version=connection.graph_api_version,
            phone_number_id=connection.phone_number_id,
            access_token=secret.value.decode("utf-8"),
        )
        try:
            templates = await client.list_templates(waba_id=connection.waba_id)
        except WhatsAppCloudApiClientError as error:
            await self._record_failure(
                tenant_id=tenant_id,
                connection_id=connection_id,
                occurred_at=occurred_at,
                audit_context=audit_context,
                reason_code="provider_unavailable",
            )
            raise ProviderTemplatesSyncHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=False,
            ) from error

        now = self.clock()
        uow = self.uow_factory()
        async with uow:
            synced_count = 0
            for item in templates:
                approval_status = _APPROVAL_STATUS_MAP.get(
                    item.approval_status,
                    ProviderTemplateApprovalStatus.PENDING,
                )
                template_record = ProviderMessageTemplateRecord(
                    id=self.uuid_factory(),
                    tenant_id=tenant_id,
                    whatsapp_connection_id=connection.id,
                    provider_template_id=item.provider_template_id,
                    name=item.name,
                    language_code=item.language_code,
                    category=item.category,
                    approval_status=approval_status,
                    component_shape=item.component_shape,
                    parameter_count=item.parameter_count,
                    last_synced_at=now,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
                await uow.provider_message_templates.upsert(record=template_record)
                synced_count += 1

            await append_required_audit_event(
                uow.audit_events,
                provider_templates_sync_completed_event(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                    operation_count=synced_count,
                ),
            )
            await uow.commit()

    async def _record_failure(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        occurred_at: datetime,
        audit_context: AuditContext,
        reason_code: str,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            try:
                await append_required_audit_event(
                    uow.audit_events,
                    provider_templates_sync_failed_event(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        occurred_at=occurred_at,
                        audit_context=audit_context,
                        actor_type=AuditActorType.SERVICE,
                        actor_id=self.service_actor_id,
                        event_id=self.uuid_factory(),
                        reason_code=reason_code,
                    ),
                )
                await uow.commit()
            except Exception:
                await uow.rollback()
