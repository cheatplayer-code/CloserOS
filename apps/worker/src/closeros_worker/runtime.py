"""Worker runtime composition for outbox ingestion processing."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from closeros.application.ai_budget_service import AiBudgetService
from closeros.application.ai_gateway import AiGateway as NopqAiGateway
from closeros.application.ai_gateway import KnowledgeRetrievalPort
from closeros.application.ai_input_gate import AiInputGate
from closeros.application.ai_output_validator import AiOutputValidator
from closeros.application.ai_ports import (
    AiClock,
    AiCredentialResolver,
    AiProvider,
    AiProviderRegistry,
)
from closeros.application.ai_prompt_builder import AiPromptBuilder
from closeros.application.analysis_enqueue_service import AnalysisEnqueueService
from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.content_redact_handler import ContentRedactHandler
from closeros.application.conversation_input_assembler import ConversationInputAssembler
from closeros.application.csv_import_processor import CsvImportProcessor
from closeros.application.encryption_ports import RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_index_handler import KnowledgeIndexHandler
from closeros.application.knowledge_retrieval import (
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalService,
)
from closeros.application.knowledge_search_key import DevKnowledgeSearchKeyProvider
from closeros.application.message_analyze_handler import MessageAnalyzeHandler
from closeros.application.metrics_engine import MetricsEngine
from closeros.application.metrics_enqueue_service import MetricsEnqueueService
from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandler
from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
from closeros.application.outbox_processor import OutboxJobHandler, OutboxProcessorService
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.application.outbox_reconciliation import OutboxReconciliationService
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.application.webhook_normalize_handler import WebhookNormalizeHandler
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose
from closeros.domain.audit import AuditActorType
from closeros.domain.knowledge import KnowledgeRetrievalResult
from closeros.domain.outbox import OutboxJobKind
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.redis_stream_queue import (
    RedisStreamJobConsumer,
    RedisStreamQueuePublisher,
)
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import (
    StaticKeyProvider,
    require_production_key_provider,
)
from closeros.infrastructure.synthetic_hmac_adapter import SyntheticHmacWebhookAdapter
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from closeros_worker.settings import WorkerConfigurationError, WorkerSettings

NOPQ_SUPPORTED_JOB_KINDS = frozenset(
    {
        OutboxJobKind.WEBHOOK_NORMALIZE,
        OutboxJobKind.CSV_IMPORT,
        OutboxJobKind.CONTENT_REDACT,
        OutboxJobKind.METRICS_RECALCULATE,
        OutboxJobKind.KNOWLEDGE_INDEX,
        OutboxJobKind.MESSAGE_ANALYZE,
    }
)
LM_SUPPORTED_JOB_KINDS = NOPQ_SUPPORTED_JOB_KINDS

_DEV_KEK_V1 = bytes(range(32))
_DEV_KEY_VERSION = "dev-kek-v1"


class ProductionProviderAdaptersRequiredError(RuntimeError):
    """Raised when production worker composition lacks explicit provider adapters."""


class _WorkerAiClock(AiClock):
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class _WorkerAiProviderRegistry(AiProviderRegistry):
    providers: dict[AiProviderCode, AiProvider]

    def get_provider(self, *, provider_code: AiProviderCode) -> AiProvider:
        provider = self.providers.get(provider_code)
        if provider is None:
            raise RuntimeError("provider not configured")
        return provider


class _WorkerAiCredentialResolver(AiCredentialResolver):
    async def resolve_bearer_key(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_code: AiProviderCode,
    ) -> str | None:
        _ = tenant_id
        if provider_code is AiProviderCode.SYNTHETIC:
            return "synthetic-local-key"
        raw = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        return raw or None


@dataclass(frozen=True, slots=True)
class _GatewayKnowledgeRetrievalAdapter(KnowledgeRetrievalPort):
    retrieval_service: KnowledgeRetrievalService
    service_actor_id: uuid.UUID
    uuid_factory: Callable[[], uuid.UUID]
    clock: _WorkerAiClock

    async def retrieve_for_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        purpose: AiPurpose,
        query_text: str,
        max_chunks: int,
    ) -> tuple[KnowledgeRetrievalResult, ...]:
        if purpose is not AiPurpose.CONVERSATION_ANALYSIS:
            return ()
        result = await self.retrieval_service.retrieve(
            KnowledgeRetrievalRequest(
                tenant_id=tenant_id,
                query_text=query_text,
                analysis_target_id=self.uuid_factory(),
                occurred_at=self.clock.now(),
                audit_context=AuditContext(correlation_id=self.uuid_factory()),
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                limit=max_chunks,
            )
        )
        return tuple(result)


def require_production_provider_adapters(
    registry: ProviderAdapterRegistry | None,
) -> ProviderAdapterRegistry:
    if registry is None:
        raise ProductionProviderAdaptersRequiredError(
            "production requires explicit provider adapter registry injection"
        )
    return registry


@dataclass
class WorkerRuntimeOverrides:
    key_provider: StaticKeyProvider | None = None
    adapter_registry: ProviderAdapterRegistry | None = None
    ingestion_service_id: uuid.UUID | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork] | None = None
    redis: Redis | None = None


@dataclass
class WorkerRuntime:
    settings: WorkerSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork]
    queue_publisher: RedisStreamQueuePublisher
    queue_consumer: RedisStreamJobConsumer
    publisher_service_factory: Callable[[], OutboxPublisherService]
    processor_service_factory: Callable[[], OutboxProcessorService]
    reconciliation_service_factory: Callable[[], OutboxReconciliationService]
    handlers: dict[OutboxJobKind, OutboxJobHandler]

    async def dispose(self) -> None:
        await self.queue_publisher.close()
        await self.queue_consumer.close()
        await self.engine.dispose()


def _development_key_provider() -> StaticKeyProvider:
    return StaticKeyProvider(
        keys_by_version={_DEV_KEY_VERSION: _DEV_KEK_V1},
        active_version=_DEV_KEY_VERSION,
    )


def _development_webhook_secret() -> bytes:
    raw_value = os.environ.get("SYNTHETIC_WEBHOOK_SECRET", "").strip()
    if raw_value:
        return raw_value.encode("utf-8")
    return bytes(range(32))


def _development_adapter_registry() -> ProviderAdapterRegistry:
    return ProviderAdapterRegistry(
        adapters=(SyntheticHmacWebhookAdapter(secret=_development_webhook_secret()),),
    )


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _ingestion_service_id(settings: WorkerSettings, override: uuid.UUID | None) -> uuid.UUID:
    if override is not None:
        return override
    raw_value = os.environ.get("INGESTION_SERVICE_ID", "").strip()
    if raw_value:
        return uuid.UUID(raw_value)
    if settings.is_development:
        return uuid.uuid4()
    raise WorkerConfigurationError("INGESTION_SERVICE_ID is not set")


def build_worker_runtime(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None = None,
) -> WorkerRuntime:
    override_values = overrides or WorkerRuntimeOverrides()

    if settings.is_production:
        key_provider = cast(
            StaticKeyProvider,
            require_production_key_provider(override_values.key_provider),
        )
        adapter_registry = require_production_provider_adapters(override_values.adapter_registry)
    else:
        key_provider = override_values.key_provider or _development_key_provider()
        adapter_registry = override_values.adapter_registry or _development_adapter_registry()

    engine = override_values.engine
    session_factory = override_values.session_factory
    if session_factory is None:
        if engine is None:
            engine = create_authentication_engine(normalize_database_url(settings.database_url))
        session_factory = create_authentication_sessionmaker(engine)

    integrated_uow_factory = override_values.integrated_uow_factory
    if integrated_uow_factory is None:

        def integrated_uow_factory() -> SqlAlchemyIntegratedUnitOfWork:
            return SqlAlchemyIntegratedUnitOfWork(session_factory)

    integrated_port_factory = cast(
        Callable[[], IntegratedUnitOfWork],
        integrated_uow_factory,
    )

    content_encryption = ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=key_provider,
            secure_random=OsSecureRandom(),
        ),
        retention_expiry_calculator=RetentionExpiryCalculator(),
        uow_factory=integrated_port_factory,
    )
    atomic_content_commands = AtomicContentCommandService(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
    )
    service_actor_id = _ingestion_service_id(settings, override_values.ingestion_service_id)

    webhook_handler = WebhookNormalizeHandler(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
        adapter_registry=adapter_registry,
        atomic_commands=atomic_content_commands,
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    csv_import_handler = CsvImportProcessor(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    metrics_enqueue = MetricsEnqueueService(
        uow_factory=integrated_port_factory,
        uuid_factory=uuid.uuid4,
        service_actor_id=service_actor_id,
    )
    analysis_enqueue = AnalysisEnqueueService(
        uow_factory=integrated_port_factory,
        uuid_factory=uuid.uuid4,
    )
    content_redact_handler = ContentRedactHandler(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
        metrics_enqueue=metrics_enqueue,
        analysis_enqueue=analysis_enqueue,
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    metrics_recalculate_handler = MetricsRecalculateHandler(
        uow_factory=integrated_port_factory,
        metrics_engine=MetricsEngine(),
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    knowledge_index_handler = KnowledgeIndexHandler(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
        key_provider=DevKnowledgeSearchKeyProvider(),
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    ai_clock = _WorkerAiClock()
    retrieval_service = KnowledgeRetrievalService(
        uow_factory=integrated_port_factory,
        key_provider=DevKnowledgeSearchKeyProvider(),
        content_encryption=content_encryption,
        uuid_factory=uuid.uuid4,
    )
    ai_gateway = NopqAiGateway(
        external_calls_enabled=_bool_env("AI_EXTERNAL_CALLS_ENABLED", default=False),
        clock=ai_clock,
        input_gate=AiInputGate(),
        assembler=ConversationInputAssembler(),
        prompt_builder=AiPromptBuilder(),
        output_validator=AiOutputValidator(),
        budget_service=AiBudgetService(),
        provider_registry=_WorkerAiProviderRegistry(
            providers={
                AiProviderCode.SYNTHETIC: SyntheticAiProvider(),
                AiProviderCode.OPENAI_COMPATIBLE: OpenAICompatibleChatAdapter(
                    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/"),
                    provider_code=AiProviderCode.OPENAI_COMPATIBLE,
                ),
            }
        ),
        credential_resolver=_WorkerAiCredentialResolver(),
        knowledge_retrieval=_GatewayKnowledgeRetrievalAdapter(
            retrieval_service=retrieval_service,
            service_actor_id=service_actor_id,
            uuid_factory=uuid.uuid4,
            clock=ai_clock,
        ),
    )
    message_analyze_handler = MessageAnalyzeHandler(
        uow_factory=integrated_port_factory,
        content_encryption=content_encryption,
        ai_gateway=ai_gateway,
        service_actor_id=service_actor_id,
        provider_code=AiProviderCode.SYNTHETIC
        if settings.is_development
        else AiProviderCode.OPENAI_COMPATIBLE,
        uuid_factory=uuid.uuid4,
        clock=ai_clock.now,
    )
    handlers: dict[OutboxJobKind, OutboxJobHandler] = {
        OutboxJobKind.WEBHOOK_NORMALIZE: webhook_handler,
        OutboxJobKind.CSV_IMPORT: csv_import_handler,
        OutboxJobKind.CONTENT_REDACT: content_redact_handler,
        OutboxJobKind.METRICS_RECALCULATE: metrics_recalculate_handler,
        OutboxJobKind.KNOWLEDGE_INDEX: knowledge_index_handler,
        OutboxJobKind.MESSAGE_ANALYZE: message_analyze_handler,
    }

    redis = override_values.redis or Redis.from_url(settings.redis_url, decode_responses=False)
    queue_publisher = RedisStreamQueuePublisher(redis=redis, stream_name=settings.outbox_stream)
    queue_consumer = RedisStreamJobConsumer(
        redis=redis,
        stream_name=settings.outbox_stream,
        group_name=settings.outbox_consumer_group,
        consumer_name=settings.worker_id,
        block_ms=settings.processor_block_ms,
    )

    def publisher_service_factory() -> OutboxPublisherService:
        uow = integrated_uow_factory()
        return OutboxPublisherService(
            outbox_jobs=uow.outbox_jobs,
            outbox_job_attempts=uow.outbox_job_attempts,
            queue_publisher=queue_publisher,
            worker_id=settings.worker_id,
        )

    def processor_service_factory() -> OutboxProcessorService:
        uow = integrated_uow_factory()
        return OutboxProcessorService(
            outbox_jobs=uow.outbox_jobs,
            outbox_job_attempts=uow.outbox_job_attempts,
            handlers=handlers,
            worker_id=settings.worker_id,
            supported_job_kinds=NOPQ_SUPPORTED_JOB_KINDS,
        )

    def reconciliation_service_factory() -> OutboxReconciliationService:
        uow = integrated_uow_factory()
        return OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)

    if engine is None:
        raise RuntimeError("worker engine is required")

    return WorkerRuntime(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        integrated_uow_factory=integrated_uow_factory,
        queue_publisher=queue_publisher,
        queue_consumer=queue_consumer,
        publisher_service_factory=publisher_service_factory,
        processor_service_factory=processor_service_factory,
        reconciliation_service_factory=reconciliation_service_factory,
        handlers=handlers,
    )
