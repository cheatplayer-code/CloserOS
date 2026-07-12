"""Mappers between WhatsApp domain, records, and ORM rows."""

from __future__ import annotations

from closeros.application.whatsapp_persistence import WhatsAppCloudConnectionRecord
from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.provider_capability import ProviderCapability
from closeros.domain.whatsapp_cloud_connection import (
    WebhookSubscriptionStatus,
    WhatsAppCloudConnection,
    WhatsAppCloudConnectionStatus,
)
from closeros.infrastructure.whatsapp_orm import WhatsAppCloudConnectionRow


def _capabilities_to_json(capabilities: frozenset[ProviderCapability]) -> list[str]:
    return sorted(capability.value for capability in capabilities)


def _capabilities_from_json(values: list[str]) -> frozenset[ProviderCapability]:
    return frozenset(ProviderCapability(value) for value in values)


def record_to_domain(record: WhatsAppCloudConnectionRecord) -> WhatsAppCloudConnection:
    return WhatsAppCloudConnection(
        id=record.id,
        tenant_id=record.tenant_id,
        channel_connection_id=record.channel_connection_id,
        provider=ProviderKind.WHATSAPP_CLOUD,
        app_id=record.app_id,
        waba_id=record.waba_id,
        phone_number_id=record.phone_number_id,
        display_phone_number=record.display_phone_number,
        graph_api_version=record.graph_api_version,
        access_token_ref=record.access_token_ref,
        app_secret_ref=record.app_secret_ref,
        verify_token_ref=record.verify_token_ref,
        status=record.status,
        webhook_subscription_status=record.webhook_subscription_status,
        capabilities=record.capabilities,
        webhook_public_key=record.webhook_public_key,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_verified_at=record.last_verified_at,
        version=record.version,
    )


def domain_to_record(connection: WhatsAppCloudConnection) -> WhatsAppCloudConnectionRecord:
    return WhatsAppCloudConnectionRecord(
        id=connection.id,
        tenant_id=connection.tenant_id,
        channel_connection_id=connection.channel_connection_id,
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


def record_to_row(record: WhatsAppCloudConnectionRecord) -> WhatsAppCloudConnectionRow:
    return WhatsAppCloudConnectionRow(
        id=record.id,
        tenant_id=record.tenant_id,
        channel_connection_id=record.channel_connection_id,
        provider=ProviderKind.WHATSAPP_CLOUD.value,
        app_id=record.app_id,
        waba_id=record.waba_id,
        phone_number_id=record.phone_number_id,
        display_phone_number=record.display_phone_number,
        graph_api_version=record.graph_api_version,
        access_token_ref=record.access_token_ref,
        app_secret_ref=record.app_secret_ref,
        verify_token_ref=record.verify_token_ref,
        status=record.status.value,
        webhook_subscription_status=record.webhook_subscription_status.value,
        capabilities=_capabilities_to_json(record.capabilities),
        webhook_public_key=record.webhook_public_key,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_verified_at=record.last_verified_at,
        version=record.version,
    )


def row_to_record(row: WhatsAppCloudConnectionRow) -> WhatsAppCloudConnectionRecord:
    return WhatsAppCloudConnectionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_connection_id=row.channel_connection_id,
        app_id=row.app_id,
        waba_id=row.waba_id,
        phone_number_id=row.phone_number_id,
        display_phone_number=row.display_phone_number,
        graph_api_version=row.graph_api_version,
        access_token_ref=row.access_token_ref,
        app_secret_ref=row.app_secret_ref,
        verify_token_ref=row.verify_token_ref,
        status=WhatsAppCloudConnectionStatus(row.status),
        webhook_subscription_status=WebhookSubscriptionStatus(row.webhook_subscription_status),
        capabilities=_capabilities_from_json(row.capabilities),
        webhook_public_key=row.webhook_public_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_verified_at=row.last_verified_at,
        version=row.version,
    )
