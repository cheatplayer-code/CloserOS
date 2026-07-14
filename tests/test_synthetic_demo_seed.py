"""PostgreSQL integration tests for synthetic demo seeding."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID, uuid4

import pytest
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.bootstrap_tenant_service import BootstrapTenantService
from closeros.application.outbox_persistence import OutboxReconciliationFilter
from closeros.application.persistence_errors import TenantMismatchError
from closeros.application.synthetic_demo_seed_service import (
    SyntheticDemoSeedService,
    demo_uuid,
    synthetic_external_connection_id,
)
from closeros.domain.authentication import AuthenticationEmail
from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.identity import Role
from closeros.domain.outbox import OutboxJobKind, OutboxJobState
from sqlalchemy import text

from tests.auth_persistence_support import synthetic_credential, synthetic_user
from tests.encryption_support import build_content_encryption_service

pytestmark = pytest.mark.z0_persistence

OWNER_EMAIL = "seed.owner@example.invalid"
OWNER_USER_ID = UUID("00000000-0000-0000-0000-00000000b001")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-00000000b002")
PLAINTEXT_MARKER = b"[Synthetic Demo]"


def _bootstrap_service(integrated_uow_factory: Any) -> BootstrapTenantService:
    return BootstrapTenantService(
        uow_factory=integrated_uow_factory,
        uuid_factory=uuid4,
        clock=lambda: synthetic_credential().created_at,
    )


def _seed_service(integrated_uow_factory: Any) -> SyntheticDemoSeedService:
    content_encryption = build_content_encryption_service(integrated_uow_factory)
    return SyntheticDemoSeedService(
        uow_factory=integrated_uow_factory,
        content_encryption=content_encryption,
        atomic_commands=AtomicContentCommandService(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
        ),
        service_actor_id=UUID("00000000-0000-0000-0000-00000000e001"),
        uuid_factory=uuid4,
        clock=lambda: synthetic_credential().created_at,
    )


async def _seed_verified_owner(integrated_uow_factory: Any) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.users.add(synthetic_user(user_id=OWNER_USER_ID))
        credential = synthetic_credential(
            user_id=OWNER_USER_ID,
            email=AuthenticationEmail(OWNER_EMAIL),
        )
        credential = credential.__class__(
            id=credential.id,
            user_id=credential.user_id,
            email=credential.email,
            password_hash=credential.password_hash,
            created_at=credential.created_at,
            email_verified_at=credential.created_at,
        )
        await uow.credentials.add(credential)
        await uow.commit()


async def _bootstrap_demo_tenant(integrated_uow_factory: Any) -> UUID:
    await _seed_verified_owner(integrated_uow_factory)
    result = await _bootstrap_service(integrated_uow_factory).bootstrap_owner_tenant(
        owner_email=OWNER_EMAIL,
        tenant_name="Synthetic Demo Tenant",
        time_zone="Asia/Almaty",
    )
    return result.tenant_id


def test_synthetic_seed_creates_demo_graph(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        result = await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        assert result.status == "created"
        assert result.conversation_threads == 6
        assert result.follow_up_tasks == 2
        assert result.managers == 2

    asyncio.run(exercise())


def test_synthetic_seed_does_not_store_plaintext_in_encrypted_table(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        uow = integrated_uow_factory()
        async with uow:
            rows = (
                await uow.session.execute(
                    text("SELECT ciphertext FROM encrypted_contents WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
            ).all()
        assert rows
        for row in rows:
            assert PLAINTEXT_MARKER not in row.ciphertext

    asyncio.run(exercise())


def test_synthetic_seed_is_tenant_scoped(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        uow = integrated_uow_factory()
        async with uow:
            with pytest.raises(TenantMismatchError):
                await uow.conversation_threads.get_by_id(
                    tenant_id=OTHER_TENANT_ID,
                    thread_id=demo_uuid(tenant_id, "thread-0"),
                )
        uow = integrated_uow_factory()
        async with uow:
            local_thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=demo_uuid(tenant_id, "thread-0"),
            )
        assert local_thread is not None

    asyncio.run(exercise())


def test_synthetic_seed_is_idempotent(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        service = _seed_service(integrated_uow_factory)
        first = await service.seed_demo(tenant_id=tenant_id)
        second = await service.seed_demo(tenant_id=tenant_id)
        assert first.status == "created"
        assert second.status == "existing"
        uow = integrated_uow_factory()
        async with uow:
            connection = await uow.channel_connections.get_by_provider_external_id(
                tenant_id=tenant_id,
                provider=ProviderKind.SYNTHETIC,
                external_connection_id=synthetic_external_connection_id(tenant_id),
            )
        assert connection is not None

    asyncio.run(exercise())


def test_synthetic_seed_generates_outbox_jobs(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        uow = integrated_uow_factory()
        async with uow:
            jobs = await uow.outbox_jobs.list_by_state(
                state=OutboxJobState.SUCCEEDED,
                query_filter=OutboxReconciliationFilter(tenant_id=tenant_id, limit=500),
            )
        kinds = {job.job_kind for job in jobs}
        assert OutboxJobKind.CONTENT_REDACT in kinds
        assert OutboxJobKind.MESSAGE_ANALYZE in kinds
        assert OutboxJobKind.METRICS_RECALCULATE in kinds

    asyncio.run(exercise())


def test_synthetic_seed_uses_synthetic_provider_without_external_ai(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        os.environ["AI_EXTERNAL_CALLS_ENABLED"] = "false"
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        uow = integrated_uow_factory()
        async with uow:
            runs = await uow.conversation_analysis_runs.list_by_tenant(
                tenant_id=tenant_id,
                limit=10,
            )
        assert runs
        assert all(run.model_provider == "local" for run in runs)

    asyncio.run(exercise())


def test_synthetic_seed_populates_product_queries(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        from closeros.application.audit_recording import AuditContext
        from closeros.application.dashboard_query_service import DashboardQueryService
        from closeros.application.metrics_query_service import MetricsQueryService
        from closeros.application.metrics_windows import (
            local_date_from_timestamp,
            rolling_30_day_window_for_local_date,
        )
        from closeros.application.scorecard_query_service import ScorecardQueryService
        from closeros.domain.audit import AuditActorType

        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        seed_now = synthetic_credential().created_at
        await _seed_service(integrated_uow_factory).seed_demo(tenant_id=tenant_id)
        audit_context = AuditContext(correlation_id=uuid4())
        window = rolling_30_day_window_for_local_date(
            local_date=local_date_from_timestamp(occurred_at=seed_now, time_zone="Asia/Almaty"),
            time_zone="Asia/Almaty",
        )
        dashboard_service = DashboardQueryService(
            uow_factory=integrated_uow_factory,
            metrics_query_service=MetricsQueryService(uow_factory=integrated_uow_factory),
            uuid_factory=uuid4,
            clock=lambda: seed_now,
        )
        dashboard = await dashboard_service.get_dashboard(
            tenant_id=tenant_id,
            window_start=window.start,
            window_end=window.end,
            audit_context=audit_context,
            actor_type=AuditActorType.SERVICE,
            actor_id=OWNER_USER_ID,
        )
        assert dashboard.total_conversations >= 1
        uow = integrated_uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_tenant(tenant_id)
            manager_membership = next(
                membership for membership in memberships if Role.MANAGER in membership.roles
            )
        scorecard_service = ScorecardQueryService(
            uow_factory=integrated_uow_factory,
            metrics_query_service=MetricsQueryService(uow_factory=integrated_uow_factory),
            uuid_factory=uuid4,
            clock=lambda: seed_now,
        )
        scorecard = await scorecard_service.get_scorecard(
            tenant_id=tenant_id,
            membership_id=manager_membership.id,
            roles=frozenset({Role.OWNER}),
            actor_user_id=OWNER_USER_ID,
            window_start=window.start,
            window_end=window.end,
            audit_context=audit_context,
            actor_type=AuditActorType.SERVICE,
            actor_id=OWNER_USER_ID,
        )
        assert scorecard is not None
        assert scorecard.manager_user_id == manager_membership.user_id
        assert scorecard.manager_user_id != manager_membership.id
        assert scorecard.composite_basis_points >= 0
        assert (
            scorecard.components.response_rate_basis_points > 0
            or scorecard.components.conversion_rate_basis_points > 0
            or scorecard.components.task_completion_basis_points > 0
        )

    asyncio.run(exercise())


def test_synthetic_seed_reset_preserves_real_message_and_task(
    integrated_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        from closeros.application.audit_recording import AuditContext
        from closeros.application.follow_up_task_persistence import FollowUpTaskRecord
        from closeros.application.synthetic_demo_reset import SyntheticDemoResetError
        from closeros.domain.adapter_metadata import AdapterMetadata
        from closeros.domain.audit import AuditActorType
        from closeros.domain.canonical_enums import (
            ChannelConnectionStatus,
            MessageDirection,
            ParticipantSenderType,
            ProviderKind,
        )
        from closeros.domain.channel_connection import ChannelConnection
        from closeros.domain.conversation_thread import ConversationThread
        from closeros.domain.follow_up_task import FollowUpTaskPriority, FollowUpTaskStatus

        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        service = _seed_service(integrated_uow_factory)
        await service.seed_demo(tenant_id=tenant_id)

        seed_now = synthetic_credential().created_at
        real_message_id = uuid4()
        real_content_id = uuid4()
        real_task_id = uuid4()
        real_connection_id = uuid4()
        real_thread_id = uuid4()

        uow = integrated_uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_tenant(tenant_id)
            owner_membership = next(
                membership for membership in memberships if Role.OWNER in membership.roles
            )
            await uow.channel_connections.add(
                ChannelConnection(
                    id=real_connection_id,
                    tenant_id=tenant_id,
                    provider=ProviderKind.SYNTHETIC,
                    external_connection_id=f"real-connection-{tenant_id}",
                    status=ChannelConnectionStatus.ACTIVE,
                    adapter_metadata=AdapterMetadata.from_mapping({"source": "real"}),
                    created_at=seed_now,
                    updated_at=seed_now,
                )
            )
            await uow.conversation_threads.add(
                ConversationThread(
                    id=real_thread_id,
                    tenant_id=tenant_id,
                    channel_connection_id=real_connection_id,
                    external_conversation_id="real-thread",
                    sales_case_id=None,
                    lifecycle_status=None,
                    adapter_metadata=AdapterMetadata.from_mapping({"source": "real"}),
                    created_at=seed_now,
                    updated_at=seed_now,
                )
            )
            await uow.follow_up_tasks.add(
                record=FollowUpTaskRecord(
                    id=real_task_id,
                    tenant_id=tenant_id,
                    conversation_thread_id=real_thread_id,
                    source_finding_id=None,
                    title="Real follow-up task",
                    status=FollowUpTaskStatus.OPEN,
                    priority=FollowUpTaskPriority.NORMAL,
                    assigned_membership_id=owner_membership.id,
                    created_by_user_id=OWNER_USER_ID,
                    due_at=None,
                    completed_at=None,
                    cancelled_at=None,
                    created_at=seed_now,
                    updated_at=seed_now,
                    version=1,
                )
            )
            await uow.commit()

        content_encryption = build_content_encryption_service(integrated_uow_factory)
        atomic = AtomicContentCommandService(
            uow_factory=integrated_uow_factory,
            content_encryption=content_encryption,
        )
        await atomic.store_raw_message(
            tenant_id=tenant_id,
            content_id=real_content_id,
            message_id=real_message_id,
            outbox_job_id=uuid4(),
            audit_event_id=uuid4(),
            conversation_thread_id=real_thread_id,
            external_message_id=f"real-msg-{real_message_id}",
            sender_type=ParticipantSenderType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            sent_at=seed_now,
            received_at=seed_now,
            reply_to_message_id=None,
            adapter_metadata=AdapterMetadata.from_mapping({"source": "real"}),
            plaintext=b"real customer message body",
            created_at=seed_now,
            occurred_at=seed_now,
            audit_context=AuditContext(correlation_id=uuid4()),
            actor_type=AuditActorType.USER,
            actor_id=OWNER_USER_ID,
        )

        await service.reset_demo(tenant_id=tenant_id, dry_run=False)

        uow = integrated_uow_factory()
        async with uow:
            assert (
                await uow.messages.get_by_id(tenant_id=tenant_id, message_id=real_message_id)
                is not None
            )
            assert (
                await uow.follow_up_tasks.get_by_id(tenant_id=tenant_id, task_id=real_task_id)
                is not None
            )
            assert (
                await uow.conversation_threads.get_by_id(
                    tenant_id=tenant_id,
                    thread_id=demo_uuid(tenant_id, "thread-0"),
                )
                is None
            )

        with pytest.raises(SyntheticDemoResetError):
            await service.reset_demo(tenant_id=tenant_id, dry_run=False)

    asyncio.run(exercise())


def test_synthetic_reset_dry_run_does_not_delete(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        tenant_id = await _bootstrap_demo_tenant(integrated_uow_factory)
        service = _seed_service(integrated_uow_factory)
        await service.seed_demo(tenant_id=tenant_id)
        plan = await service.reset_demo(tenant_id=tenant_id, dry_run=True)
        assert plan is not None
        assert getattr(plan, "total_resources", 0) > 0
        uow = integrated_uow_factory()
        async with uow:
            thread = await uow.conversation_threads.get_by_id(
                tenant_id=tenant_id,
                thread_id=demo_uuid(tenant_id, "thread-0"),
            )
        assert thread is not None

    asyncio.run(exercise())
