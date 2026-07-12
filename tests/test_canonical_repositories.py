"""PostgreSQL integration tests for canonical repositories."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from closeros.application.canonical_persistence import CanonicalPersistenceError
from closeros.application.persistence_errors import TenantMismatchError
from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    SalesCaseStatus,
    WebhookProcessingStatus,
)

from tests.canonical_persistence_support import (
    CHANNEL_CONNECTION_A_ID,
    CHANNEL_CONNECTION_B_ID,
    CONTENT_A_ID,
    CONTENT_B_ID,
    CRM_OUTCOME_A_ID,
    DELETION_EVENT_A_ID,
    EDIT_EVENT_A_ID,
    MESSAGE_A_ID,
    MESSAGE_B_ID,
    SALES_CASE_A_ID,
    THREAD_A_ID,
    WEBHOOK_EVENT_A_ID,
    synthetic_channel_connection,
    synthetic_conversation_thread,
    synthetic_crm_outcome,
    synthetic_lead,
    synthetic_manager_assignment,
    synthetic_message,
    synthetic_message_deletion_event,
    synthetic_message_edit_event,
    synthetic_sales_case,
    synthetic_webhook_event,
)
from tests.encryption_support import seed_canonical_encrypted_content_stubs
from tests.tenant_persistence_support import TENANT_A_ID, TENANT_B_ID, synthetic_tenant

pytestmark = pytest.mark.platform_persistence


async def _seed_channel_graph(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    uow = platform_uow_factory()
    async with uow:
        await uow.tenants.add(synthetic_tenant())
        await uow.commit()

    await seed_canonical_encrypted_content_stubs(
        integrated_uow_factory,
        tenant_id=TENANT_A_ID,
        content_ids=(CONTENT_A_ID, CONTENT_B_ID),
    )

    canonical = canonical_uow_factory()
    async with canonical:
        await canonical.channel_connections.add(synthetic_channel_connection())
        await canonical.sales_cases.add(synthetic_sales_case())
        await canonical.conversation_threads.add(
            synthetic_conversation_thread(sales_case_id=SALES_CASE_A_ID, lifecycle_status=None)
        )
        await canonical.commit()


def test_channel_connection_repository_round_trip(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(synthetic_channel_connection())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            by_id = await lookup.channel_connections.get_by_id(
                tenant_id=TENANT_A_ID,
                connection_id=CHANNEL_CONNECTION_A_ID,
            )
            by_external = await lookup.channel_connections.get_by_provider_external_id(
                tenant_id=TENANT_A_ID,
                provider=synthetic_channel_connection().provider,
                external_connection_id="wa-conn-synthetic-001",
            )

        assert by_id is not None
        assert by_external is not None
        assert by_id.external_connection_id == "wa-conn-synthetic-001"

    asyncio.run(exercise())


def test_channel_connection_repository_enforces_idempotency(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(synthetic_channel_connection())
            with pytest.raises(CanonicalPersistenceError):
                await write.channel_connections.add(
                    synthetic_channel_connection(connection_id=CHANNEL_CONNECTION_B_ID)
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_lead_repository_round_trip(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.leads.add(synthetic_lead())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.leads.get_by_external_identity_id(
                tenant_id=TENANT_A_ID,
                external_identity_id="lead-synthetic-001",
            )

        assert restored is not None
        assert restored.external_identity_id == "lead-synthetic-001"

    asyncio.run(exercise())


def test_message_repository_append_and_lookup(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.messages.get_by_external_message_id(
                tenant_id=TENANT_A_ID,
                conversation_thread_id=THREAD_A_ID,
                external_message_id="msg-synthetic-001",
            )

        assert restored is not None
        assert restored.id == MESSAGE_A_ID

    asyncio.run(exercise())


def test_message_repository_enforces_external_idempotency(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            with pytest.raises(CanonicalPersistenceError):
                await write.messages.append(
                    synthetic_message(message_id=MESSAGE_B_ID),
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_message_event_repositories_append_and_lookup(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            await write.message_edit_events.append(synthetic_message_edit_event())
            await write.message_deletion_events.append(synthetic_message_deletion_event())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            edit = await lookup.message_edit_events.get_by_id(
                tenant_id=TENANT_A_ID,
                event_id=EDIT_EVENT_A_ID,
            )
            deletion = await lookup.message_deletion_events.get_by_id(
                tenant_id=TENANT_A_ID,
                event_id=DELETION_EVENT_A_ID,
            )

        assert edit is not None
        assert deletion is not None

    asyncio.run(exercise())


def test_message_edit_event_repository_enforces_idempotency(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            await write.message_edit_events.append(synthetic_message_edit_event())
            with pytest.raises(CanonicalPersistenceError):
                await write.message_edit_events.append(
                    synthetic_message_edit_event(
                        event_id=UUID("00000000-0000-0000-0000-000000000610"),
                        external_event_id="edit-synthetic-001",
                    )
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_message_deletion_event_repository_enforces_idempotency(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            await write.message_deletion_events.append(synthetic_message_deletion_event())
            with pytest.raises(CanonicalPersistenceError):
                await write.message_deletion_events.append(
                    synthetic_message_deletion_event(
                        event_id=UUID("00000000-0000-0000-0000-000000000611"),
                        external_event_id="delete-synthetic-001",
                    )
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_conversation_thread_repository_rejects_cross_tenant_channel_connection(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.tenants.add(
                synthetic_tenant(tenant_id=TENANT_B_ID, name="Synthetic Tenant B")
            )
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(synthetic_channel_connection())
            with pytest.raises(CanonicalPersistenceError):
                await write.conversation_threads.add(
                    synthetic_conversation_thread(tenant_id=TENANT_B_ID)
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_message_repository_denies_cross_tenant_lookup(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.messages.append(synthetic_message())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            with pytest.raises(TenantMismatchError, match="tenant scope mismatch"):
                await lookup.messages.get_by_id(
                    tenant_id=TENANT_B_ID,
                    message_id=MESSAGE_A_ID,
                )

    asyncio.run(exercise())


def test_manager_assignment_and_crm_outcome_repositories(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        write = canonical_uow_factory()
        async with write:
            await write.manager_assignments.append(
                synthetic_manager_assignment(
                    conversation_thread_id=None,
                    sales_case_id=SALES_CASE_A_ID,
                )
            )
            await write.crm_outcomes.append(synthetic_crm_outcome())
            await write.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            outcome = await lookup.crm_outcomes.get_by_id(
                tenant_id=TENANT_A_ID,
                outcome_id=CRM_OUTCOME_A_ID,
            )

        assert outcome is not None
        assert outcome.external_deal_id == "deal-synthetic-001"

    asyncio.run(exercise())


def test_webhook_event_repository_round_trip_and_status_update(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(synthetic_channel_connection())
            await write.webhook_events.append(synthetic_webhook_event())
            await write.commit()

        update = canonical_uow_factory()
        async with update:
            await update.webhook_events.update_processing_status(
                tenant_id=TENANT_A_ID,
                event_id=WEBHOOK_EVENT_A_ID,
                processing_status=WebhookProcessingStatus.PROCESSED,
                processed_at=synthetic_webhook_event().received_at,
            )
            await update.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.webhook_events.get_by_external_event_id(
                tenant_id=TENANT_A_ID,
                channel_connection_id=CHANNEL_CONNECTION_A_ID,
                external_event_id="webhook-synthetic-001",
            )

        assert restored is not None
        assert restored.processing_status is WebhookProcessingStatus.PROCESSED

    asyncio.run(exercise())


def test_webhook_event_repository_enforces_idempotency(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(synthetic_channel_connection())
            await write.webhook_events.append(synthetic_webhook_event())
            with pytest.raises(CanonicalPersistenceError):
                await write.webhook_events.append(
                    synthetic_webhook_event(
                        event_id=UUID("00000000-0000-0000-0000-000000000901"),
                    )
                )
                await write.commit()
            await write.rollback()

    asyncio.run(exercise())


def test_channel_connection_update_persists_status(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        connection = synthetic_channel_connection()
        write = canonical_uow_factory()
        async with write:
            await write.channel_connections.add(connection)
            await write.commit()

        updated = synthetic_channel_connection(status=ChannelConnectionStatus.DEGRADED)
        update = canonical_uow_factory()
        async with update:
            await update.channel_connections.update(updated)
            await update.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.channel_connections.get_by_id(
                tenant_id=TENANT_A_ID,
                connection_id=CHANNEL_CONNECTION_A_ID,
            )

        assert restored is not None
        assert restored.status is ChannelConnectionStatus.DEGRADED

    asyncio.run(exercise())


def test_conversation_thread_repository_get_by_external_id(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        await _seed_channel_graph(
            canonical_uow_factory,
            platform_uow_factory,
            integrated_uow_factory,
        )

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.conversation_threads.get_by_external_conversation_id(
                tenant_id=TENANT_A_ID,
                channel_connection_id=CHANNEL_CONNECTION_A_ID,
                external_conversation_id="thread-synthetic-001",
            )

        assert restored is not None
        assert restored.sales_case_id == SALES_CASE_A_ID
        assert restored.lifecycle_status is None

    asyncio.run(exercise())


def test_sales_case_repository_update_persists_status(
    canonical_uow_factory: Any,
    platform_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = platform_uow_factory()
        async with uow:
            await uow.tenants.add(synthetic_tenant())
            await uow.commit()

        write = canonical_uow_factory()
        async with write:
            await write.sales_cases.add(synthetic_sales_case())
            await write.commit()

        updated = synthetic_sales_case(status=SalesCaseStatus.QUALIFIED)
        update = canonical_uow_factory()
        async with update:
            await update.sales_cases.update(updated)
            await update.commit()

        lookup = canonical_uow_factory()
        async with lookup:
            restored = await lookup.sales_cases.get_by_id(
                tenant_id=TENANT_A_ID,
                sales_case_id=SALES_CASE_A_ID,
            )

        assert restored is not None
        assert restored.status is SalesCaseStatus.QUALIFIED

    asyncio.run(exercise())
