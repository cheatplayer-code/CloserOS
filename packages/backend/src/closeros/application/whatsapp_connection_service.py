"""Application service for WhatsApp Cloud connection lifecycle."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.provider_ports import WhatsAppCredentialResolver
from closeros.application.whatsapp_audit import (
    whatsapp_connection_created_event,
    whatsapp_connection_disabled_event,
    whatsapp_connection_verified_event,
)
from closeros.application.whatsapp_persistence import (
    WhatsAppConnectionNotFoundError,
    WhatsAppConnectionVersionConflictError,
)
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import ChannelConnectionStatus, ProviderKind
from closeros.domain.channel_connection import ChannelConnection
from closeros.domain.provider_capability import ProviderCapability
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnection,
    WhatsAppCloudConnectionStatus,
    connection_requires_credentials,
)
from closeros.infrastructure import whatsapp_mappers as mappers
from closeros.infrastructure.whatsapp_cloud_api_client import (
    WhatsAppCloudApiClient,
    WhatsAppCloudApiClientError,
    build_client_for_connection,
)

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]
_VerifyClientFactory = Callable[
    [WhatsAppCloudConnection, str],
    WhatsAppCloudApiClient,
]


class WhatsAppConnectionServiceError(Exception):
    """Raised when WhatsApp connection operations cannot be completed."""


class WhatsAppConnectionAccessDeniedError(WhatsAppConnectionServiceError):
    """Raised when caller lacks permission for the operation."""


_DEFAULT_CAPABILITIES = frozenset(
    {
        ProviderCapability.INBOUND_TEXT,
        ProviderCapability.INTERACTIVE_REPLY,
        ProviderCapability.REACTION,
        ProviderCapability.MESSAGE_STATUS,
        ProviderCapability.MEDIA_REFERENCE,
        ProviderCapability.OUTBOUND_FREE_FORM_TEXT,
        ProviderCapability.OUTBOUND_APPROVED_TEMPLATE,
    }
)


class WhatsAppConnectionService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        credential_resolver: WhatsAppCredentialResolver,
        uuid_factory: _UuidFactory,
        clock: _Clock,
        client_factory: _VerifyClientFactory | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._credential_resolver = credential_resolver
        self._uuid_factory = uuid_factory
        self._clock = clock
        self._client_factory = client_factory or (
            lambda connection, access_token: build_client_for_connection(
                graph_api_version=connection.graph_api_version,
                phone_number_id=connection.phone_number_id,
                access_token=access_token,
            )
        )

    async def create_connection(
        self,
        *,
        tenant_id: UUID,
        channel_connection_id: UUID,
        app_id: str,
        waba_id: str,
        phone_number_id: str,
        display_phone_number: str | None,
        graph_api_version: str,
        access_token_ref: str | None,
        app_secret_ref: str | None,
        verify_token_ref: str | None,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> WhatsAppCloudConnection:
        now = self._clock()
        connection_id = self._uuid_factory()
        channel_connection = ChannelConnection(
            id=channel_connection_id,
            tenant_id=tenant_id,
            provider=ProviderKind.WHATSAPP_CLOUD,
            external_connection_id=phone_number_id,
            status=ChannelConnectionStatus.DRAFT,
            adapter_metadata=AdapterMetadata.from_mapping({"provider": "whatsapp_cloud"}),
            created_at=now,
            updated_at=now,
        )
        connection = WhatsAppCloudConnection(
            id=connection_id,
            tenant_id=tenant_id,
            channel_connection_id=channel_connection_id,
            provider=ProviderKind.WHATSAPP_CLOUD,
            app_id=app_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone_number,
            graph_api_version=graph_api_version,
            access_token_ref=access_token_ref,
            app_secret_ref=app_secret_ref,
            verify_token_ref=verify_token_ref,
            status=WhatsAppCloudConnectionStatus.DRAFT,
            webhook_subscription_status=WebhookSubscriptionStatus.NOT_CONFIGURED,
            capabilities=_DEFAULT_CAPABILITIES,
            webhook_public_key=secrets.token_hex(32),
            created_at=now,
            updated_at=now,
            last_verified_at=None,
            version=1,
        )
        uow = self._uow_factory()
        async with uow:
            existing_channel = await uow.channel_connections.get_by_id(
                tenant_id=tenant_id,
                connection_id=channel_connection_id,
            )
            if existing_channel is None:
                await uow.channel_connections.add(channel_connection)
            elif existing_channel.provider is not ProviderKind.WHATSAPP_CLOUD:
                raise WhatsAppConnectionServiceError("channel connection unavailable")
            await uow.whatsapp_cloud_connections.add(record=mappers.domain_to_record(connection))
            await append_required_audit_event(
                uow.audit_events,
                whatsapp_connection_created_event(
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

    async def update_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        app_id: str,
        waba_id: str,
        phone_number_id: str,
        display_phone_number: str | None,
        graph_api_version: str,
        access_token_ref: str | None,
        app_secret_ref: str | None,
        verify_token_ref: str | None,
        expected_version: int,
    ) -> WhatsAppCloudConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.whatsapp_cloud_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise WhatsAppConnectionNotFoundError("whatsapp connection not found")
            domain = mappers.record_to_domain(current)
            updated = replace(
                domain,
                app_id=app_id,
                waba_id=waba_id,
                phone_number_id=phone_number_id,
                display_phone_number=display_phone_number,
                graph_api_version=graph_api_version,
                access_token_ref=access_token_ref,
                app_secret_ref=app_secret_ref,
                verify_token_ref=verify_token_ref,
                updated_at=now,
                version=domain.version + 1,
            )
            updated = _revalidate_connection(updated)
            try:
                persisted = await uow.whatsapp_cloud_connections.update(
                    record=mappers.domain_to_record(updated),
                    expected_version=expected_version,
                )
            except WhatsAppConnectionVersionConflictError as error:
                raise WhatsAppConnectionServiceError("operation unavailable") from error
            await uow.commit()
        return mappers.record_to_domain(persisted)

    async def verify_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> WhatsAppCloudConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.whatsapp_cloud_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise WhatsAppConnectionNotFoundError("whatsapp connection not found")
            domain = mappers.record_to_domain(current)
            if domain.status is WhatsAppCloudConnectionStatus.DISABLED:
                raise WhatsAppConnectionServiceError("connection disabled")

            access_token = await self._resolve_access_token(domain)
            if access_token is None:
                raise WhatsAppConnectionServiceError("credentials unavailable")

            client = self._client_factory(domain, access_token)
            try:
                phone_config = await client.verify_phone_config()
            except WhatsAppCloudApiClientError as error:
                await append_required_audit_event(
                    uow.audit_events,
                    whatsapp_connection_verified_event(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        occurred_at=now,
                        audit_context=audit_context,
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_id=self._uuid_factory(),
                        outcome="failed",
                    ),
                )
                await uow.commit()
                raise WhatsAppConnectionServiceError("verification failed") from error

            updated = replace(
                domain,
                status=WhatsAppCloudConnectionStatus.ACTIVE,
                webhook_subscription_status=WebhookSubscriptionStatus.SUBSCRIBED,
                display_phone_number=phone_config.display_phone_number
                or domain.display_phone_number,
                last_verified_at=now,
                updated_at=now,
                version=domain.version + 1,
            )
            updated = _revalidate_connection(updated)
            try:
                persisted = await uow.whatsapp_cloud_connections.update(
                    record=mappers.domain_to_record(updated),
                    expected_version=expected_version,
                )
            except WhatsAppConnectionVersionConflictError as error:
                raise WhatsAppConnectionServiceError("operation unavailable") from error
            await append_required_audit_event(
                uow.audit_events,
                whatsapp_connection_verified_event(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_id=self._uuid_factory(),
                    outcome="verified",
                ),
            )
            await uow.commit()
        return mappers.record_to_domain(persisted)

    async def disable_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
        actor_type: AuditActorType,
        actor_id: UUID | None,
    ) -> WhatsAppCloudConnection:
        now = self._clock()
        uow = self._uow_factory()
        async with uow:
            current = await uow.whatsapp_cloud_connections.get_by_id_for_update(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if current is None:
                raise WhatsAppConnectionNotFoundError("whatsapp connection not found")
            domain = mappers.record_to_domain(current)
            updated = replace(
                domain,
                status=WhatsAppCloudConnectionStatus.DISABLED,
                webhook_subscription_status=WebhookSubscriptionStatus.FAILED,
                updated_at=now,
                version=domain.version + 1,
            )
            updated = _revalidate_connection(updated)
            try:
                persisted = await uow.whatsapp_cloud_connections.update(
                    record=mappers.domain_to_record(updated),
                    expected_version=expected_version,
                )
            except WhatsAppConnectionVersionConflictError as error:
                raise WhatsAppConnectionServiceError("operation unavailable") from error
            await append_required_audit_event(
                uow.audit_events,
                whatsapp_connection_disabled_event(
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
        return mappers.record_to_domain(persisted)

    async def list_connections(self, *, tenant_id: UUID) -> tuple[WhatsAppCloudConnection, ...]:
        uow = self._uow_factory()
        async with uow:
            records = await uow.whatsapp_cloud_connections.list_by_tenant(tenant_id=tenant_id)
        return tuple(mappers.record_to_domain(record) for record in records)

    async def get_connection(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> WhatsAppCloudConnection | None:
        uow = self._uow_factory()
        async with uow:
            record = await uow.whatsapp_cloud_connections.get_by_id(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
        return None if record is None else mappers.record_to_domain(record)

    async def _resolve_access_token(self, connection: WhatsAppCloudConnection) -> str | None:
        if not connection_requires_credentials(connection.status):
            return None
        if connection.access_token_ref is None:
            return None
        secret = await self._credential_resolver.resolve_access_token(
            tenant_id=connection.tenant_id,
            whatsapp_connection_id=connection.id,
            reference_key=connection.access_token_ref,
        )
        return None if secret is None else secret.value.decode("utf-8")


def _revalidate_connection(connection: WhatsAppCloudConnection) -> WhatsAppCloudConnection:
    return WhatsAppCloudConnection(
        id=connection.id,
        tenant_id=connection.tenant_id,
        channel_connection_id=connection.channel_connection_id,
        provider=connection.provider,
        app_id=connection.app_id,
        waba_id=connection.waba_id,
        phone_number_id=connection.phone_number_id,
        display_phone_number=connection.display_phone_number,
        graph_api_version=connection.graph_api_version,
        access_token_ref=connection.access_token_ref,
        app_secret_ref=connection.app_secret_ref,
        verify_token_ref=connection.verify_token_ref,
        status=connection.status,
        webhook_subscription_status=connection.webhook_subscription_status,
        capabilities=connection.capabilities,
        webhook_public_key=connection.webhook_public_key,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        last_verified_at=connection.last_verified_at,
        version=connection.version,
    )
