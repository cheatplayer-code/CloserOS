"""Operator seed for bounded synthetic product demonstration data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import text

from closeros.application.ai_budget_service import AiBudgetService
from closeros.application.ai_gateway import AiGateway, KnowledgeRetrievalPort
from closeros.application.ai_input_gate import AiInputGate
from closeros.application.ai_output_validator import AiOutputValidator
from closeros.application.ai_ports import AiCredentialResolver, AiProviderRegistry
from closeros.application.ai_prompt_builder import AiPromptBuilder
from closeros.application.analysis_enqueue_service import AnalysisEnqueueService
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.content_redact_handler import ContentRedactHandler
from closeros.application.conversation_input_assembler import ConversationInputAssembler
from closeros.application.follow_up_task_persistence import FollowUpTaskRecord
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.message_analyze_handler import MessageAnalyzeHandler
from closeros.application.metrics_engine import MetricsEngine
from closeros.application.metrics_enqueue_service import MetricsEnqueueService
from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandler
from closeros.application.outbox_persistence import OutboxReconciliationFilter
from closeros.application.outbox_processor import OutboxProcessorService
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.application.synthetic_demo_reset import (
    SyntheticDemoResetError,
    SyntheticDemoResetService,
)
from closeros.domain.adapter_metadata import AdapterMetadata
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose
from closeros.domain.audit import AuditActorType
from closeros.domain.canonical_enums import (
    ChannelConnectionStatus,
    CrmOutcomeType,
    LeadStatus,
    MessageDirection,
    ParticipantSenderType,
    ProviderKind,
    SalesCaseStatus,
)
from closeros.domain.channel_connection import ChannelConnection
from closeros.domain.conversation_thread import ConversationThread
from closeros.domain.crm_outcome import CRMOutcome
from closeros.domain.follow_up_task import FollowUpTaskPriority, FollowUpTaskStatus
from closeros.domain.identity import MembershipStatus, Role, UserStatus
from closeros.domain.knowledge import KnowledgeRetrievalResult
from closeros.domain.lead import Lead
from closeros.domain.manager_assignment import ManagerAssignment
from closeros.domain.membership import Membership
from closeros.domain.outbox import OutboxJob, OutboxJobKind, OutboxJobState
from closeros.domain.sales_case import SalesCase
from closeros.domain.synthetic_seed import (
    RESOURCE_DELETION_ORDER,
    SyntheticManagerIdentity,
    SyntheticSeedManifest,
    SyntheticSeedResetState,
    SyntheticSeedResource,
    SyntheticSeedResourceType,
)
from closeros.domain.user import User
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork

SYNTHETIC_DEMO_VERSION = "synthetic-demo-v1"
SYNTHETIC_DEMO_NAMESPACE = UUID("c3f5a7b2-4e1d-4f8a-9b6c-2d7e9f1a3b5c")
THREAD_COUNT = 6

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]


class SyntheticDemoSeedError(Exception):
    """Base class for synthetic demo seed failures."""


class SyntheticDemoTenantNotFoundError(SyntheticDemoSeedError):
    """Raised when the target tenant does not exist."""


class SyntheticDemoOwnerMissingError(SyntheticDemoSeedError):
    """Raised when the tenant has no active owner membership."""


@dataclass(frozen=True, slots=True)
class SyntheticDemoSeedResult:
    status: str
    tenant_id: UUID
    conversation_threads: int
    follow_up_tasks: int
    managers: int


def synthetic_external_connection_id(tenant_id: UUID) -> str:
    return f"{SYNTHETIC_DEMO_VERSION}-{tenant_id}"


def demo_uuid(tenant_id: UUID, key: str) -> UUID:
    return uuid5(SYNTHETIC_DEMO_NAMESPACE, f"{SYNTHETIC_DEMO_VERSION}:{tenant_id}:{key}")


def demo_adapter_metadata(*, key: str) -> AdapterMetadata:
    return AdapterMetadata.from_mapping(
        {
            "source": "synthetic_demo",
            "provider_ref": SYNTHETIC_DEMO_VERSION,
            "demo_key": key,
        }
    )


class _SyntheticCredentialResolver(AiCredentialResolver):
    async def resolve_bearer_key(
        self,
        *,
        tenant_id: UUID,
        provider_code: AiProviderCode,
    ) -> str | None:
        _ = tenant_id
        if provider_code is AiProviderCode.SYNTHETIC:
            return "synthetic-local-key"
        return None


class _SyntheticProviderRegistry(AiProviderRegistry):
    def get_provider(self, *, provider_code: AiProviderCode) -> SyntheticAiProvider:
        if provider_code is not AiProviderCode.SYNTHETIC:
            raise RuntimeError("synthetic demo only supports the synthetic provider")
        return SyntheticAiProvider()


class _NoKnowledgeRetrieval:
    async def retrieve_for_conversation(
        self,
        *,
        tenant_id: UUID,
        purpose: AiPurpose,
        query_text: str,
        max_chunks: int,
    ) -> tuple[KnowledgeRetrievalResult, ...]:
        _ = (tenant_id, purpose, query_text, max_chunks)
        return ()


class _WorkerClock:
    def __init__(self, clock: _Clock) -> None:
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()


@dataclass(frozen=True, slots=True)
class _DemoPipeline:
    content_redact: ContentRedactHandler
    message_analyze: MessageAnalyzeHandler
    metrics_recalculate: MetricsRecalculateHandler


def build_synthetic_demo_pipeline(
    *,
    uow_factory: _UnitOfWorkFactory,
    content_encryption: ContentEncryptionService,
    service_actor_id: UUID,
    uuid_factory: _UuidFactory,
    clock: _Clock,
) -> _DemoPipeline:
    metrics_enqueue = MetricsEnqueueService(
        uow_factory=uow_factory,
        uuid_factory=uuid_factory,
        service_actor_id=service_actor_id,
    )
    analysis_enqueue = AnalysisEnqueueService(
        uow_factory=uow_factory,
        uuid_factory=uuid_factory,
    )
    worker_clock = _WorkerClock(clock)
    ai_gateway = AiGateway(
        external_calls_enabled=True,
        clock=worker_clock,
        input_gate=AiInputGate(),
        assembler=ConversationInputAssembler(),
        prompt_builder=AiPromptBuilder(),
        output_validator=AiOutputValidator(),
        budget_service=AiBudgetService(),
        provider_registry=_SyntheticProviderRegistry(),
        credential_resolver=_SyntheticCredentialResolver(),
        knowledge_retrieval=cast(KnowledgeRetrievalPort, _NoKnowledgeRetrieval()),
    )
    return _DemoPipeline(
        content_redact=ContentRedactHandler(
            uow_factory=uow_factory,
            content_encryption=content_encryption,
            metrics_enqueue=metrics_enqueue,
            analysis_enqueue=analysis_enqueue,
            service_actor_id=service_actor_id,
            uuid_factory=uuid_factory,
        ),
        message_analyze=MessageAnalyzeHandler(
            uow_factory=uow_factory,
            content_encryption=content_encryption,
            ai_gateway=ai_gateway,
            service_actor_id=service_actor_id,
            provider_code=AiProviderCode.SYNTHETIC,
            uuid_factory=uuid_factory,
            clock=clock,
        ),
        metrics_recalculate=MetricsRecalculateHandler(
            uow_factory=uow_factory,
            metrics_engine=MetricsEngine(),
            service_actor_id=service_actor_id,
            uuid_factory=uuid_factory,
        ),
    )


class SyntheticDemoProvenanceIncompleteError(SyntheticDemoSeedError):
    """Raised when provenance is missing or inconsistent for a reset."""


class SyntheticDemoResetConflictError(SyntheticDemoSeedError):
    """Raised when reset cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class _PendingResource:
    resource_type: SyntheticSeedResourceType
    resource_id: UUID


class _SeedResourceLedger:
    def __init__(self, *, tenant_id: UUID, manifest_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.manifest_id = manifest_id
        self._items: list[_PendingResource] = []
        self._seen: set[tuple[SyntheticSeedResourceType, UUID]] = set()

    def add(self, *, resource_type: SyntheticSeedResourceType, resource_id: UUID) -> None:
        key = (resource_type, resource_id)
        if key in self._seen:
            return
        self._seen.add(key)
        self._items.append(_PendingResource(resource_type=resource_type, resource_id=resource_id))

    def as_records(self, *, uuid_factory: _UuidFactory) -> tuple[SyntheticSeedResource, ...]:
        return tuple(
            SyntheticSeedResource(
                id=uuid_factory(),
                tenant_id=self.tenant_id,
                manifest_id=self.manifest_id,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                deletion_order=RESOURCE_DELETION_ORDER[item.resource_type],
            )
            for item in self._items
        )


class _InlineQueuePublisher:
    async def publish_job_id(self, *, job_id: UUID) -> None:
        _ = job_id

    async def close(self) -> None:
        return None


class SyntheticDemoSeedService:
    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        content_encryption: ContentEncryptionService,
        atomic_commands: AtomicContentCommandService,
        service_actor_id: UUID,
        uuid_factory: _UuidFactory,
        clock: _Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._content_encryption = content_encryption
        self._atomic_commands = atomic_commands
        self._service_actor_id = service_actor_id
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def seed_demo(
        self,
        *,
        tenant_id: UUID,
        reset_existing: bool = False,
        dry_run_reset: bool = False,
    ) -> SyntheticDemoSeedResult:
        await self._ensure_tenant_ready(tenant_id=tenant_id)
        existing = await self._find_existing_connection(tenant_id=tenant_id)
        if existing is not None and not reset_existing:
            return await self._existing_result(tenant_id=tenant_id)

        if reset_existing:
            reset_service = SyntheticDemoResetService(
                uow_factory=self._uow_factory,
                seed_version=SYNTHETIC_DEMO_VERSION,
            )
            try:
                await reset_service.reset(tenant_id=tenant_id, dry_run=dry_run_reset)
            except SyntheticDemoResetError as error:
                if existing is not None:
                    raise SyntheticDemoProvenanceIncompleteError(str(error)) from error
            if dry_run_reset:
                return await self._existing_result(tenant_id=tenant_id)

        owner_user_id = await self._load_owner_user_id(tenant_id=tenant_id)
        now = self._clock()
        seed_run_id = self._uuid_factory()
        manifest_id = demo_uuid(tenant_id, f"manifest-{seed_run_id}")
        ledger = _SeedResourceLedger(tenant_id=tenant_id, manifest_id=manifest_id)
        pipeline = build_synthetic_demo_pipeline(
            uow_factory=self._uow_factory,
            content_encryption=self._content_encryption,
            service_actor_id=self._service_actor_id,
            uuid_factory=self._uuid_factory,
            clock=self._clock,
        )

        manager_identities = await self._create_managers(
            tenant_id=tenant_id,
            now=now,
            ledger=ledger,
        )
        connection_id = await self._create_connection(
            tenant_id=tenant_id,
            now=now,
            ledger=ledger,
        )
        await self._create_ai_policy(tenant_id=tenant_id, now=now, ledger=ledger)
        thread_ids = await self._create_conversation_graph(
            tenant_id=tenant_id,
            connection_id=connection_id,
            manager_identities=manager_identities,
            owner_user_id=owner_user_id,
            now=now,
            ledger=ledger,
        )
        await self._process_outbox_pipeline(
            tenant_id=tenant_id,
            pipeline=pipeline,
            ledger=ledger,
        )
        finding_id = await self._first_open_finding_id(tenant_id=tenant_id)
        task_count = await self._create_follow_up_tasks(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            thread_ids=thread_ids,
            manager_membership_id=manager_identities[0].membership_id,
            finding_id=finding_id,
            now=now,
            ledger=ledger,
        )
        await self._enqueue_and_process_metrics(
            tenant_id=tenant_id,
            pipeline=pipeline,
            now=now,
            ledger=ledger,
        )
        await self._collect_derived_resources(tenant_id=tenant_id, ledger=ledger)
        await self._persist_manifest(
            tenant_id=tenant_id,
            manifest_id=manifest_id,
            seed_run_id=seed_run_id,
            now=now,
            ledger=ledger,
        )

        return SyntheticDemoSeedResult(
            status="created",
            tenant_id=tenant_id,
            conversation_threads=len(thread_ids),
            follow_up_tasks=task_count,
            managers=len(manager_identities),
        )

    async def _ensure_tenant_ready(self, *, tenant_id: UUID) -> None:
        uow = self._uow_factory()
        async with uow:
            tenant = await uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise SyntheticDemoTenantNotFoundError("tenant does not exist")

    async def _find_existing_connection(self, *, tenant_id: UUID) -> ChannelConnection | None:
        uow = self._uow_factory()
        async with uow:
            return await uow.channel_connections.get_by_provider_external_id(
                tenant_id=tenant_id,
                provider=ProviderKind.SYNTHETIC,
                external_connection_id=synthetic_external_connection_id(tenant_id),
            )

    async def _existing_result(self, *, tenant_id: UUID) -> SyntheticDemoSeedResult:
        from closeros.application.follow_up_task_persistence import FollowUpTaskListFilter

        uow = self._uow_factory()
        async with uow:
            threads = 0
            for index in range(THREAD_COUNT):
                thread = await uow.conversation_threads.get_by_id(
                    tenant_id=tenant_id,
                    thread_id=demo_uuid(tenant_id, f"thread-{index}"),
                )
                if thread is not None:
                    threads += 1
            tasks_page = await uow.follow_up_tasks.list_page(
                filters=FollowUpTaskListFilter(tenant_id=tenant_id),
                limit=50,
                cursor=None,
            )
            demo_task_ids = {
                demo_uuid(tenant_id, "task-open"),
                demo_uuid(tenant_id, "task-done"),
            }
            demo_tasks = tuple(item for item in tasks_page.items if item.id in demo_task_ids)
        return SyntheticDemoSeedResult(
            status="existing",
            tenant_id=tenant_id,
            conversation_threads=threads,
            follow_up_tasks=len(demo_tasks),
            managers=2,
        )

    async def _load_owner_user_id(self, *, tenant_id: UUID) -> UUID:
        uow = self._uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_tenant(tenant_id)
            for membership in memberships:
                if Role.OWNER in membership.roles and membership.status is MembershipStatus.ACTIVE:
                    return membership.user_id
        raise SyntheticDemoOwnerMissingError("tenant has no active owner membership")

    async def _create_managers(
        self,
        *,
        tenant_id: UUID,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> tuple[SyntheticManagerIdentity, SyntheticManagerIdentity]:
        manager_specs = (
            ("manager-a", "manager-a.demo.example.invalid"),
            ("manager-b", "manager-b.demo.example.invalid"),
        )
        identities: list[SyntheticManagerIdentity] = []
        uow = self._uow_factory()
        async with uow:
            for key, _email in manager_specs:
                user_id = demo_uuid(tenant_id, f"{key}-user")
                membership_id = demo_uuid(tenant_id, f"{key}-membership")
                await uow.users.add(User(id=user_id, status=UserStatus.ACTIVE))
                await uow.memberships.add(
                    Membership(
                        id=membership_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        roles=frozenset({Role.MANAGER}),
                        status=MembershipStatus.ACTIVE,
                    )
                )
                ledger.add(
                    resource_type=SyntheticSeedResourceType.USER,
                    resource_id=user_id,
                )
                ledger.add(
                    resource_type=SyntheticSeedResourceType.MEMBERSHIP,
                    resource_id=membership_id,
                )
                identities.append(
                    SyntheticManagerIdentity(user_id=user_id, membership_id=membership_id)
                )
            await uow.commit()
        return identities[0], identities[1]

    async def _create_connection(
        self,
        *,
        tenant_id: UUID,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> UUID:
        connection_id = demo_uuid(tenant_id, "connection")
        connection = ChannelConnection(
            id=connection_id,
            tenant_id=tenant_id,
            provider=ProviderKind.SYNTHETIC,
            external_connection_id=synthetic_external_connection_id(tenant_id),
            status=ChannelConnectionStatus.ACTIVE,
            adapter_metadata=demo_adapter_metadata(key="connection"),
            created_at=now,
            updated_at=now,
        )
        uow = self._uow_factory()
        async with uow:
            await uow.channel_connections.add(connection)
            await uow.commit()
        ledger.add(
            resource_type=SyntheticSeedResourceType.CHANNEL_CONNECTION,
            resource_id=connection_id,
        )
        return connection_id

    async def _create_ai_policy(
        self,
        *,
        tenant_id: UUID,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> None:
        from closeros.application.ai_policy_persistence import TenantAiPolicyRecord

        policy_id = demo_uuid(tenant_id, "ai-policy")
        record = TenantAiPolicyRecord(
            id=policy_id,
            tenant_id=tenant_id,
            mode="enforce",
            prompt_version="synthetic-demo-prompt-v1",
            rubric_version="synthetic-demo-rubric-v1",
            minimum_confidence_basis_points=5000,
            daily_budget_limit_minor_units=100_000,
            monthly_budget_limit_minor_units=1_000_000,
            created_at=now,
            updated_at=now,
        )
        uow = self._uow_factory()
        async with uow:
            await uow.tenant_ai_policies.upsert(record=record)
            await uow.commit()
        ledger.add(
            resource_type=SyntheticSeedResourceType.TENANT_AI_POLICY,
            resource_id=policy_id,
        )

    async def _create_conversation_graph(
        self,
        *,
        tenant_id: UUID,
        connection_id: UUID,
        manager_identities: tuple[SyntheticManagerIdentity, SyntheticManagerIdentity],
        owner_user_id: UUID,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> tuple[UUID, ...]:
        thread_ids: list[UUID] = []
        audit_context = AuditContext(correlation_id=demo_uuid(tenant_id, "seed-correlation"))
        base = now - timedelta(days=7)

        scenarios: tuple[
            tuple[str, SalesCaseStatus, str, tuple[tuple[str, str, str, int], ...]], ...
        ] = (
            (
                "thread-0",
                SalesCaseStatus.WON,
                "won",
                (
                    ("customer", "inbound", "Pricing question for Acme Fictional Suite", 0),
                    ("manager", "outbound", "Shared quote for demo tenant only", 2),
                    ("customer", "inbound", "Approved synthetic purchase", 6),
                ),
            ),
            (
                "thread-1",
                SalesCaseStatus.LOST,
                "lost",
                (
                    ("customer", "inbound", "Need integration timeline", 12),
                    ("manager", "outbound", "Offered callback slot", 14),
                    ("customer", "inbound", "Chose another vendor in demo", 30),
                ),
            ),
            (
                "thread-2",
                SalesCaseStatus.AWAITING_CUSTOMER,
                "delayed",
                (
                    ("customer", "inbound", "Can you confirm demo shipment date?", 36),
                    ("manager", "outbound", "Delayed manager response after four hours", 40),
                ),
            ),
            (
                "thread-3",
                SalesCaseStatus.QUALIFIED,
                "finding",
                (
                    ("customer", "inbound", "What is included in onboarding?", 48),
                    ("manager", "outbound", "We will send details soon", 50),
                ),
            ),
            (
                "thread-4",
                SalesCaseStatus.APPOINTMENT_PROPOSED,
                "active-a",
                (
                    ("customer", "inbound", "Book demo for team at example.invalid", 54),
                    ("manager", "outbound", "Proposed Tuesday slot", 56),
                ),
            ),
            (
                "thread-5",
                SalesCaseStatus.AWAITING_BUSINESS,
                "active-b",
                (("customer", "inbound", "Need manager callback +00000000001", 60),),
            ),
        )

        for index, (thread_key, case_status, case_key, messages) in enumerate(scenarios):
            thread_id = demo_uuid(tenant_id, thread_key)
            case_id = demo_uuid(tenant_id, f"case-{case_key}")
            lead_id = demo_uuid(tenant_id, f"lead-{index}")
            thread_ids.append(thread_id)
            uow = self._uow_factory()
            async with uow:
                await uow.leads.add(
                    Lead(
                        id=lead_id,
                        tenant_id=tenant_id,
                        external_identity_id=f"synthetic-lead-{index}@lead.demo.example.invalid",
                        status=LeadStatus.ACTIVE,
                        adapter_metadata=demo_adapter_metadata(key=f"lead-{index}"),
                        created_at=base + timedelta(hours=index),
                        updated_at=base + timedelta(hours=index),
                    )
                )
                await uow.sales_cases.add(
                    SalesCase(
                        id=case_id,
                        tenant_id=tenant_id,
                        status=case_status,
                        created_at=base + timedelta(hours=index),
                        updated_at=base + timedelta(hours=index),
                    )
                )
                await uow.conversation_threads.add(
                    ConversationThread(
                        id=thread_id,
                        tenant_id=tenant_id,
                        channel_connection_id=connection_id,
                        external_conversation_id=f"synthetic-thread-{index}",
                        sales_case_id=case_id,
                        lifecycle_status=None,
                        adapter_metadata=demo_adapter_metadata(key=thread_key),
                        created_at=base + timedelta(hours=index),
                        updated_at=base + timedelta(hours=index, minutes=30),
                    )
                )
                manager = manager_identities[index % 2]
                assignment_id = demo_uuid(tenant_id, f"assignment-{index}")
                await uow.manager_assignments.append(
                    ManagerAssignment(
                        id=assignment_id,
                        tenant_id=tenant_id,
                        manager_user_id=manager.user_id,
                        conversation_thread_id=thread_id,
                        sales_case_id=None,
                        assigned_at=base + timedelta(hours=index, minutes=5),
                    )
                )
                ledger.add(resource_type=SyntheticSeedResourceType.LEAD, resource_id=lead_id)
                ledger.add(resource_type=SyntheticSeedResourceType.SALES_CASE, resource_id=case_id)
                ledger.add(
                    resource_type=SyntheticSeedResourceType.CONVERSATION_THREAD,
                    resource_id=thread_id,
                )
                ledger.add(
                    resource_type=SyntheticSeedResourceType.MANAGER_ASSIGNMENT,
                    resource_id=assignment_id,
                )
                if case_status in {SalesCaseStatus.WON, SalesCaseStatus.LOST}:
                    outcome_id = demo_uuid(tenant_id, f"crm-outcome-{case_key}")
                    await uow.crm_outcomes.append(
                        CRMOutcome(
                            id=outcome_id,
                            tenant_id=tenant_id,
                            sales_case_id=case_id,
                            external_deal_id=f"synthetic-deal-{case_key}-{tenant_id}",
                            outcome_type=(
                                CrmOutcomeType.WON
                                if case_status is SalesCaseStatus.WON
                                else CrmOutcomeType.LOST
                            ),
                            occurred_at=base + timedelta(hours=index, days=1),
                            adapter_metadata=demo_adapter_metadata(key=f"crm-{case_key}"),
                        )
                    )
                    ledger.add(
                        resource_type=SyntheticSeedResourceType.CRM_OUTCOME,
                        resource_id=outcome_id,
                    )
                await uow.commit()

            previous_message_id: UUID | None = None
            for message_index, (sender, direction_name, body, hour_offset) in enumerate(messages):
                message_id = demo_uuid(tenant_id, f"{thread_key}-message-{message_index}")
                content_id = demo_uuid(tenant_id, f"{thread_key}-content-{message_index}")
                outbox_job_id = demo_uuid(tenant_id, f"{thread_key}-outbox-redact-{message_index}")
                sent_at = base + timedelta(hours=hour_offset)
                received_at = sent_at + timedelta(minutes=1)
                if thread_key == "thread-2" and sender == "manager":
                    received_at = sent_at + timedelta(hours=4)
                await self._atomic_commands.store_raw_message(
                    tenant_id=tenant_id,
                    content_id=content_id,
                    message_id=message_id,
                    outbox_job_id=outbox_job_id,
                    audit_event_id=self._uuid_factory(),
                    conversation_thread_id=thread_id,
                    external_message_id=f"synthetic-msg-{thread_key}-{message_index}",
                    sender_type=(
                        ParticipantSenderType.CUSTOMER
                        if sender == "customer"
                        else ParticipantSenderType.MANAGER
                    ),
                    direction=(
                        MessageDirection.INBOUND
                        if direction_name == "inbound"
                        else MessageDirection.OUTBOUND
                    ),
                    sent_at=sent_at,
                    received_at=received_at,
                    reply_to_message_id=previous_message_id,
                    adapter_metadata=demo_adapter_metadata(
                        key=f"{thread_key}-message-{message_index}"
                    ),
                    plaintext=f"[Synthetic Demo] {body} contact@lead.demo.example.invalid".encode(),
                    created_at=received_at,
                    occurred_at=received_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self._service_actor_id,
                )
                ledger.add(resource_type=SyntheticSeedResourceType.MESSAGE, resource_id=message_id)
                ledger.add(
                    resource_type=SyntheticSeedResourceType.ENCRYPTED_CONTENT,
                    resource_id=content_id,
                )
                ledger.add(
                    resource_type=SyntheticSeedResourceType.OUTBOX_JOB,
                    resource_id=outbox_job_id,
                )
                previous_message_id = message_id

        return tuple(thread_ids)

    async def _process_outbox_pipeline(
        self,
        *,
        tenant_id: UUID,
        pipeline: _DemoPipeline,
        ledger: _SeedResourceLedger,
    ) -> None:
        await self._drain_jobs(
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.CONTENT_REDACT,
            handler=pipeline.content_redact,
            ledger=ledger,
        )
        await self._process_analyze_jobs(
            tenant_id=tenant_id,
            handler=pipeline.message_analyze,
            ledger=ledger,
        )
        await self._drain_jobs(
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.METRICS_RECALCULATE,
            handler=pipeline.metrics_recalculate,
            ledger=ledger,
        )

    async def _drain_jobs(
        self,
        *,
        tenant_id: UUID,
        job_kind: OutboxJobKind,
        handler: object,
        ledger: _SeedResourceLedger,
        max_rounds: int = 10,
    ) -> None:
        for _ in range(max_rounds):
            pending = await self._list_pending_jobs_for_kind(tenant_id=tenant_id, job_kind=job_kind)
            if not pending:
                return
            for job in pending:
                ledger.add(resource_type=SyntheticSeedResourceType.OUTBOX_JOB, resource_id=job.id)
            uow = self._uow_factory()
            async with uow:
                publisher = OutboxPublisherService(
                    outbox_jobs=uow.outbox_jobs,
                    outbox_job_attempts=uow.outbox_job_attempts,
                    queue_publisher=_InlineQueuePublisher(),
                    worker_id="synthetic-demo-seed",
                )
                await publisher.publish_batch(now=self._clock(), batch_size=200)
                processor = OutboxProcessorService(
                    outbox_jobs=uow.outbox_jobs,
                    outbox_job_attempts=uow.outbox_job_attempts,
                    handlers={job_kind: handler},  # type: ignore[dict-item]
                    worker_id="synthetic-demo-seed",
                    clock=_WorkerClock(self._clock),
                )
                published = await uow.outbox_jobs.list_by_state(
                    state=OutboxJobState.PUBLISHED,
                    query_filter=OutboxReconciliationFilter(tenant_id=tenant_id, limit=200),
                )
                for job in published:
                    if job.job_kind is not job_kind:
                        continue
                    await processor.process_job(job_id=job.id)
                await uow.commit()

    async def _process_analyze_jobs(
        self,
        *,
        tenant_id: UUID,
        handler: MessageAnalyzeHandler,
        ledger: _SeedResourceLedger,
    ) -> None:
        pending = await self._list_pending_jobs_for_kind(
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.MESSAGE_ANALYZE,
        )
        if not pending:
            return
        analyzed_threads: set[UUID] = set()
        selected_jobs: list[OutboxJob] = []
        for job in pending:
            ledger.add(resource_type=SyntheticSeedResourceType.OUTBOX_JOB, resource_id=job.id)
            thread_id = await self._thread_id_for_message(
                tenant_id=tenant_id,
                message_id=job.reference.resource_id,
            )
            if thread_id is not None:
                if thread_id in analyzed_threads:
                    continue
                if await self._thread_has_completed_analysis(
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                ):
                    analyzed_threads.add(thread_id)
                    continue
                analyzed_threads.add(thread_id)
            selected_jobs.append(job)
        if not selected_jobs:
            return
        uow = self._uow_factory()
        async with uow:
            publisher = OutboxPublisherService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                queue_publisher=_InlineQueuePublisher(),
                worker_id="synthetic-demo-seed",
            )
            await publisher.publish_batch(now=self._clock(), batch_size=200)
            processor = OutboxProcessorService(
                outbox_jobs=uow.outbox_jobs,
                outbox_job_attempts=uow.outbox_job_attempts,
                handlers={OutboxJobKind.MESSAGE_ANALYZE: handler},
                worker_id="synthetic-demo-seed",
                clock=_WorkerClock(self._clock),
            )
            for job in selected_jobs:
                published = await uow.outbox_jobs.get_by_id(job_id=job.id)
                if published is None or published.state is not OutboxJobState.PUBLISHED:
                    continue
                await processor.process_job(job_id=job.id)
            await uow.commit()

    async def _thread_has_completed_analysis(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
    ) -> bool:
        uow = self._uow_factory()
        async with uow:
            runs = await uow.conversation_analysis_runs.list_by_tenant(
                tenant_id=tenant_id,
                conversation_thread_id=thread_id,
                limit=10,
            )
        return any(run.status == "completed" for run in runs)

    async def _list_pending_jobs_for_kind(
        self,
        *,
        tenant_id: UUID,
        job_kind: OutboxJobKind,
    ) -> tuple[OutboxJob, ...]:
        pending = await self._list_pending_jobs(tenant_id=tenant_id)
        return tuple(job for job in pending if job.job_kind is job_kind)

    async def _thread_id_for_message(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> UUID | None:
        uow = self._uow_factory()
        async with uow:
            message = await uow.messages.get_by_id(tenant_id=tenant_id, message_id=message_id)
            if message is None:
                return None
            return message.conversation_thread_id

    async def _list_pending_jobs(self, *, tenant_id: UUID) -> tuple[OutboxJob, ...]:
        from closeros.application.outbox_persistence import OutboxReconciliationFilter

        uow = self._uow_factory()
        async with uow:
            return await uow.outbox_jobs.list_by_state(
                state=OutboxJobState.PENDING,
                query_filter=OutboxReconciliationFilter(tenant_id=tenant_id, limit=200),
            )

    async def _first_open_finding_id(self, *, tenant_id: UUID) -> UUID | None:
        uow = self._uow_factory()
        async with uow:
            runs = await uow.conversation_analysis_runs.list_by_tenant(
                tenant_id=tenant_id,
                limit=20,
            )
            for run in runs:
                findings = await uow.conversation_findings.list_by_run(
                    tenant_id=tenant_id,
                    analysis_run_id=run.id,
                )
                for finding in findings:
                    if finding.status == "open":
                        return finding.id
        return None

    async def _create_follow_up_tasks(
        self,
        *,
        tenant_id: UUID,
        owner_user_id: UUID,
        thread_ids: tuple[UUID, ...],
        manager_membership_id: UUID,
        finding_id: UUID | None,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> int:
        open_task_id = demo_uuid(tenant_id, "task-open")
        done_task_id = demo_uuid(tenant_id, "task-done")
        uow = self._uow_factory()
        async with uow:
            existing_open = await uow.follow_up_tasks.get_by_id(
                tenant_id=tenant_id,
                task_id=open_task_id,
            )
            existing_done = await uow.follow_up_tasks.get_by_id(
                tenant_id=tenant_id,
                task_id=done_task_id,
            )
            if existing_open is not None and existing_done is not None:
                return 2

        audit_context = AuditContext(correlation_id=demo_uuid(tenant_id, "task-correlation"))
        open_thread = thread_ids[3]
        if existing_open is None:
            await self._add_demo_task(
                task_id=open_task_id,
                tenant_id=tenant_id,
                conversation_thread_id=open_thread,
                title="Confirm explicit next step with lead",
                priority=FollowUpTaskPriority.HIGH,
                assigned_membership_id=manager_membership_id,
                source_finding_id=finding_id,
                due_at=now + timedelta(days=1),
                created_by_user_id=owner_user_id,
                status=FollowUpTaskStatus.OPEN,
                now=now,
                audit_context=audit_context,
            )
            ledger.add(
                resource_type=SyntheticSeedResourceType.FOLLOW_UP_TASK,
                resource_id=open_task_id,
            )
        completed_thread = thread_ids[0]
        if existing_done is None:
            await self._add_demo_task(
                task_id=done_task_id,
                tenant_id=tenant_id,
                conversation_thread_id=completed_thread,
                title="Archive won synthetic deal paperwork",
                priority=FollowUpTaskPriority.NORMAL,
                assigned_membership_id=manager_membership_id,
                source_finding_id=None,
                due_at=now - timedelta(days=1),
                created_by_user_id=owner_user_id,
                status=FollowUpTaskStatus.COMPLETED,
                now=now,
                audit_context=audit_context,
            )
            ledger.add(
                resource_type=SyntheticSeedResourceType.FOLLOW_UP_TASK,
                resource_id=done_task_id,
            )
        return 2

    async def _add_demo_task(
        self,
        *,
        task_id: UUID,
        tenant_id: UUID,
        conversation_thread_id: UUID,
        title: str,
        priority: FollowUpTaskPriority,
        assigned_membership_id: UUID,
        source_finding_id: UUID | None,
        due_at: datetime | None,
        created_by_user_id: UUID,
        status: FollowUpTaskStatus,
        now: datetime,
        audit_context: AuditContext,
    ) -> None:
        from closeros.application.product_audit import follow_up_task_created_event
        from closeros.domain.follow_up_task import FollowUpTask

        task = FollowUpTask(
            id=task_id,
            tenant_id=tenant_id,
            conversation_thread_id=conversation_thread_id,
            source_finding_id=source_finding_id,
            title=title,
            status=status,
            priority=priority,
            assigned_membership_id=assigned_membership_id,
            created_by_user_id=created_by_user_id,
            due_at=due_at,
            completed_at=now if status is FollowUpTaskStatus.COMPLETED else None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
            version=1,
        )
        uow = self._uow_factory()
        async with uow:
            await uow.follow_up_tasks.add(
                record=FollowUpTaskRecord(
                    id=task.id,
                    tenant_id=task.tenant_id,
                    conversation_thread_id=task.conversation_thread_id,
                    source_finding_id=task.source_finding_id,
                    title=task.title,
                    status=task.status,
                    priority=task.priority,
                    assigned_membership_id=task.assigned_membership_id,
                    created_by_user_id=task.created_by_user_id,
                    due_at=task.due_at,
                    completed_at=task.completed_at,
                    cancelled_at=task.cancelled_at,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    version=task.version,
                )
            )
            from closeros.application.audit_recording import append_required_audit_event

            await append_required_audit_event(
                uow.audit_events,
                follow_up_task_created_event(
                    event_id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    task_id=task_id,
                    occurred_at=now,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self._service_actor_id,
                ),
            )
            await uow.commit()

    async def _enqueue_and_process_metrics(
        self,
        *,
        tenant_id: UUID,
        pipeline: _DemoPipeline,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            tenant = await uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                return
            time_zone = tenant.time_zone
        metrics_enqueue = MetricsEnqueueService(
            uow_factory=self._uow_factory,
            uuid_factory=self._uuid_factory,
            service_actor_id=self._service_actor_id,
        )
        await metrics_enqueue.enqueue_tenant_recalculation(
            tenant_id=tenant_id,
            time_zone=time_zone,
            requested_at=now,
            audit_context=AuditContext(correlation_id=demo_uuid(tenant_id, "metrics-correlation")),
            actor_type=AuditActorType.SERVICE,
            actor_id=self._service_actor_id,
        )
        await self._drain_jobs(
            tenant_id=tenant_id,
            job_kind=OutboxJobKind.METRICS_RECALCULATE,
            handler=pipeline.metrics_recalculate,
            ledger=ledger,
        )

    async def _collect_derived_resources(
        self,
        *,
        tenant_id: UUID,
        ledger: _SeedResourceLedger,
    ) -> None:
        uow = self._uow_factory()
        async with uow:
            if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
                raise SyntheticDemoSeedError("derived resource collection requires SQLAlchemy UoW")
            content_ids = {
                item.resource_id
                for item in ledger._items
                if item.resource_type is SyntheticSeedResourceType.ENCRYPTED_CONTENT
            }
            thread_ids = {
                item.resource_id
                for item in ledger._items
                if item.resource_type is SyntheticSeedResourceType.CONVERSATION_THREAD
            }
            if content_ids:
                rows = (
                    await uow.session.execute(
                        text(
                            "SELECT id FROM content_sanitizations "
                            "WHERE tenant_id = :tenant_id AND source_content_id = ANY(:ids)"
                        ),
                        {"tenant_id": tenant_id, "ids": list(content_ids)},
                    )
                ).all()
                for row in rows:
                    ledger.add(
                        resource_type=SyntheticSeedResourceType.SANITIZATION,
                        resource_id=row.id,
                    )
            if thread_ids:
                run_rows = (
                    await uow.session.execute(
                        text(
                            "SELECT id FROM conversation_analysis_runs "
                            "WHERE tenant_id = :tenant_id "
                            "AND conversation_thread_id = ANY(:ids)"
                        ),
                        {"tenant_id": tenant_id, "ids": list(thread_ids)},
                    )
                ).all()
                run_ids = [row.id for row in run_rows]
                for run_id in run_ids:
                    ledger.add(
                        resource_type=SyntheticSeedResourceType.ANALYSIS_RUN,
                        resource_id=run_id,
                    )
                if run_ids:
                    finding_rows = (
                        await uow.session.execute(
                            text(
                                "SELECT id FROM conversation_findings "
                                "WHERE tenant_id = :tenant_id AND analysis_run_id = ANY(:ids)"
                            ),
                            {"tenant_id": tenant_id, "ids": run_ids},
                        )
                    ).all()
                    finding_ids = [row.id for row in finding_rows]
                    for finding_id in finding_ids:
                        ledger.add(
                            resource_type=SyntheticSeedResourceType.FINDING,
                            resource_id=finding_id,
                        )
                    if finding_ids:
                        evidence_rows = (
                            await uow.session.execute(
                                text(
                                    "SELECT id FROM conversation_finding_evidence "
                                    "WHERE tenant_id = :tenant_id AND finding_id = ANY(:ids)"
                                ),
                                {"tenant_id": tenant_id, "ids": finding_ids},
                            )
                        ).all()
                        for row in evidence_rows:
                            ledger.add(
                                resource_type=SyntheticSeedResourceType.FINDING_EVIDENCE,
                                resource_id=row.id,
                            )
            snapshot_rows = (
                await uow.session.execute(
                    text("SELECT id FROM metric_snapshots WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
            ).all()
            for row in snapshot_rows:
                ledger.add(
                    resource_type=SyntheticSeedResourceType.METRIC_SNAPSHOT,
                    resource_id=row.id,
                )

    async def _persist_manifest(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
        seed_run_id: UUID,
        now: datetime,
        ledger: _SeedResourceLedger,
    ) -> None:
        records = ledger.as_records(uuid_factory=self._uuid_factory)
        if not records:
            raise SyntheticDemoProvenanceIncompleteError(
                "synthetic seed produced no registered resources"
            )
        uow = self._uow_factory()
        async with uow:
            await uow.synthetic_seed_manifests.add(
                manifest=SyntheticSeedManifest(
                    id=manifest_id,
                    tenant_id=tenant_id,
                    seed_version=SYNTHETIC_DEMO_VERSION,
                    seed_run_id=seed_run_id,
                    created_at=now,
                    reset_state=SyntheticSeedResetState.ACTIVE,
                )
            )
            await uow.synthetic_seed_resources.add_many(resources=records)
            await uow.commit()

    async def plan_reset(self, *, tenant_id: UUID) -> object:
        return await SyntheticDemoResetService(
            uow_factory=self._uow_factory,
            seed_version=SYNTHETIC_DEMO_VERSION,
        ).plan_reset(tenant_id=tenant_id)

    async def reset_demo(
        self,
        *,
        tenant_id: UUID,
        dry_run: bool = False,
    ) -> object:
        return await SyntheticDemoResetService(
            uow_factory=self._uow_factory,
            seed_version=SYNTHETIC_DEMO_VERSION,
        ).reset(tenant_id=tenant_id, dry_run=dry_run)
