"""Worker runtime composition for outbox ingestion processing."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from closeros.application.crm_ports import CrmAdapter
from closeros.application.crm_reconciliation_service import CrmReconciliationService
from closeros.application.crm_sync_handler import CrmSyncHandler
from closeros.application.crm_sync_service import CrmSyncService
from closeros.application.csv_import_processor import CsvImportProcessor
from closeros.application.encryption_ports import KeyProvider, RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.kms_rewrap_service import KmsRewrapService
from closeros.application.knowledge_index_handler import KnowledgeIndexHandler
from closeros.application.knowledge_retrieval import (
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalService,
)
from closeros.application.knowledge_search_key import (
    DevKnowledgeSearchKeyProvider,
    KnowledgeSearchKeyProvider,
)
from closeros.application.legal_hold_service import LegalHoldService
from closeros.application.media_fetch_handler import MediaFetchHandler
from closeros.application.media_scan_handler import MediaScanHandler
from closeros.application.message_analyze_handler import MessageAnalyzeHandler
from closeros.application.metrics_engine import MetricsEngine
from closeros.application.metrics_enqueue_service import MetricsEnqueueService
from closeros.application.metrics_recalculate_handler import MetricsRecalculateHandler
from closeros.application.notification_deliver_handler import NotificationDeliverHandler
from closeros.application.notification_delivery_service import NotificationDeliveryService
from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
from closeros.application.optional_feature_handler import (
    OptionalFeatureDisabledHandler,
)
from closeros.application.outbox_processor import OutboxJobHandler, OutboxProcessorService
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.application.outbox_reconciliation import OutboxReconciliationService
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.provider_message_send_handler import ProviderMessageSendHandler
from closeros.application.provider_templates_sync_handler import ProviderTemplatesSyncHandler
from closeros.application.retention_purge_handler import RetentionPurgeHandler
from closeros.application.retention_purge_service import RetentionPurgeService
from closeros.application.secret_ports import SecretResolver
from closeros.application.synthetic_ai_provider import SyntheticAiProvider
from closeros.application.webhook_normalize_handler import WebhookNormalizeHandler
from closeros.application.whatsapp_reconciliation_service import WhatsAppReconciliationService
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose
from closeros.domain.audit import AuditActorType
from closeros.domain.crm_provider import CrmProviderCode
from closeros.domain.knowledge import KnowledgeRetrievalResult
from closeros.domain.outbox import OutboxJobKind
from closeros.domain.provider_credentials import SecretBytes
from closeros.domain.whatsapp_messaging_policy import WhatsAppMessagingPolicy
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.bitrix24_adapter import Bitrix24Adapter
from closeros.infrastructure.clamav_scanner_adapter import ClamAvScannerAdapter
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.env_crm_credential_resolver import EnvCrmCredentialResolver
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver
from closeros.infrastructure.env_whatsapp_credential_resolver import (
    EnvWhatsAppCredentialResolver,
)
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.notification_sender_factory import (
    build_notification_sender_sync,
    require_notification_transport_configured,
)
from closeros.infrastructure.production_feature_capabilities import (
    ProductionFeatureCapabilities,
    resolve_production_feature_capabilities,
)
from closeros.infrastructure.production_runtime import (
    ProductionSharedRuntime,
    build_production_adapter_registry,
    build_production_media_scanner,
    build_production_shared_runtime,
)
from closeros.infrastructure.redis_stream_queue import (
    RedisStreamJobConsumer,
    RedisStreamQueuePublisher,
)
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.staging_runtime import (
    StagingSharedRuntime,
    build_staging_shared_runtime,
)
from closeros.infrastructure.static_key_provider import (
    StaticKeyProvider,
    require_production_key_provider,
)
from closeros.infrastructure.synthetic_hmac_adapter import SyntheticHmacWebhookAdapter
from closeros.infrastructure.whatsapp_cloud_adapter import WhatsAppCloudWebhookAdapter
from closeros.infrastructure.whatsapp_media_fetch_adapter import WhatsAppMediaFetchAdapter
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
VW_SUPPORTED_JOB_KINDS = frozenset(
    {
        *NOPQ_SUPPORTED_JOB_KINDS,
        OutboxJobKind.PROVIDER_MESSAGE_SEND,
        OutboxJobKind.PROVIDER_TEMPLATES_SYNC,
    }
)
XY_SUPPORTED_JOB_KINDS = frozenset(
    {
        *VW_SUPPORTED_JOB_KINDS,
        OutboxJobKind.NOTIFICATION_DELIVER,
        OutboxJobKind.RETENTION_DELETE,
        OutboxJobKind.MEDIA_FETCH,
        OutboxJobKind.MEDIA_SCAN,
        OutboxJobKind.CRM_SYNC,
    }
)
LM_SUPPORTED_JOB_KINDS = XY_SUPPORTED_JOB_KINDS

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
    key_provider: KeyProvider | None = None
    adapter_registry: ProviderAdapterRegistry | None = None
    ingestion_service_id: uuid.UUID | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork] | None = None
    redis: Redis | None = None
    knowledge_search_key_provider: KnowledgeSearchKeyProvider | None = None
    capabilities: ProductionFeatureCapabilities | None = None
    secret_resolver: SecretResolver | None = None
    content_encryption: ContentEncryptionService | None = None
    media_scanner: ClamAvScannerAdapter | None = None


@dataclass
class WorkerRuntime:
    settings: WorkerSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork]
    queue_publisher: RedisStreamQueuePublisher
    queue_consumer: RedisStreamJobConsumer
    publisher_service_factory: Callable[[SqlAlchemyIntegratedUnitOfWork], OutboxPublisherService]
    processor_service_factory: Callable[[SqlAlchemyIntegratedUnitOfWork], OutboxProcessorService]
    reconciliation_service_factory: Callable[
        [SqlAlchemyIntegratedUnitOfWork], OutboxReconciliationService
    ]
    whatsapp_reconciliation_service_factory: Callable[[], WhatsAppReconciliationService]
    crm_reconciliation_service_factory: Callable[[], CrmReconciliationService]
    retention_purge_service_factory: Callable[[], RetentionPurgeService]
    kms_rewrap_service_factory: Callable[[], KmsRewrapService]
    handlers: dict[OutboxJobKind, OutboxJobHandler]
    capabilities: ProductionFeatureCapabilities | None = None

    async def dispose(self) -> None:
        await self.queue_publisher.close()
        await self.queue_consumer.close()
        await self.engine.dispose()


def _merge_managed_worker_overrides(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None,
) -> WorkerRuntimeOverrides:
    base = overrides or WorkerRuntimeOverrides()
    if not settings.is_managed:
        return base
    if overrides is not None:
        return base

    service_actor_id = _ingestion_service_id(settings, base.ingestion_service_id)
    shared: ProductionSharedRuntime | StagingSharedRuntime
    if settings.is_production:
        shared = build_production_shared_runtime(
            database_url=settings.database_url,
            ingestion_service_id=service_actor_id,
        )
    else:
        shared = build_staging_shared_runtime(database_url=settings.database_url)
    require_notification_transport_configured(app_env=settings.app_env)
    adapter_registry = build_production_adapter_registry(
        integrated_uow_factory=shared.integrated_uow_factory,
        capabilities=shared.capabilities,
    )
    media_scanner = build_production_media_scanner(capabilities=shared.capabilities)
    return replace(
        base,
        engine=shared.engine,
        session_factory=shared.session_factory,
        integrated_uow_factory=shared.integrated_uow_factory,
        key_provider=shared.key_provider,
        adapter_registry=adapter_registry,
        redis=shared.redis,
        knowledge_search_key_provider=shared.knowledge_search_key_provider,
        capabilities=shared.capabilities,
        secret_resolver=shared.secret_resolver,
        content_encryption=shared.content_encryption,
        media_scanner=media_scanner,
        ingestion_service_id=service_actor_id,
    )


def _merge_production_worker_overrides(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None,
) -> WorkerRuntimeOverrides:
    """Compatibility wrapper retained for production-composition tests."""

    if not settings.is_production:
        return overrides or WorkerRuntimeOverrides()
    return _merge_managed_worker_overrides(settings, overrides)


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


def _whatsapp_graph_api_version() -> str:
    raw_value = os.environ.get("WHATSAPP_GRAPH_API_VERSION", "v21.0").strip()
    return raw_value or "v21.0"


def _build_development_adapter_registry(
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
    credential_resolver: EnvWhatsAppCredentialResolver,
) -> ProviderAdapterRegistry:
    adapters: list[object] = [
        SyntheticHmacWebhookAdapter(secret=_development_webhook_secret()),
    ]

    async def resolve_app_secret_for_channel(
        tenant_id: uuid.UUID,
        channel_connection_id: uuid.UUID,
    ) -> SecretBytes | None:
        uow = integrated_uow_factory()
        async with uow:
            records = await uow.whatsapp_cloud_connections.list_by_tenant(tenant_id=tenant_id)
        match = next(
            (record for record in records if record.channel_connection_id == channel_connection_id),
            None,
        )
        if match is None or match.app_secret_ref is None:
            return None
        return await credential_resolver.resolve_app_secret(
            tenant_id=tenant_id,
            whatsapp_connection_id=match.id,
            reference_key=match.app_secret_ref,
        )

    adapters.append(
        WhatsAppCloudWebhookAdapter(
            resolve_app_secret_for_channel=resolve_app_secret_for_channel,
            graph_api_version=_whatsapp_graph_api_version(),
        )
    )
    return ProviderAdapterRegistry(adapters=tuple(adapters))  # type: ignore[arg-type]


def _development_adapter_registry() -> ProviderAdapterRegistry:
    return ProviderAdapterRegistry(
        adapters=(SyntheticHmacWebhookAdapter(secret=_development_webhook_secret()),),
    )


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _deepseek_base_url() -> str:
    return (
        os.environ.get("DEEPSEEK_API_BASE_URL", "").strip()
        or os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        or "https://api.deepseek.com/"
    )


def _ingestion_service_id(settings: WorkerSettings, override: uuid.UUID | None) -> uuid.UUID:
    if override is not None:
        return override
    raw_value = os.environ.get("INGESTION_SERVICE_ID", "").strip()
    if raw_value:
        return uuid.UUID(raw_value)
    if settings.is_development:
        return uuid.uuid4()
    raise WorkerConfigurationError("INGESTION_SERVICE_ID is not set")


def _development_media_access_token_resolver(
    tenant_id: uuid.UUID,
    channel_connection_id: uuid.UUID,
    media_reference_id: uuid.UUID,
) -> SecretBytes | None:
    _ = tenant_id, channel_connection_id, media_reference_id
    direct_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    if direct_token:
        return SecretBytes(direct_token.encode("utf-8"))
    reference_key = os.environ.get("WHATSAPP_ACCESS_TOKEN_REF", "").strip()
    if not reference_key:
        return None
    resolved = os.environ.get(reference_key, "").strip()
    return None if not resolved else SecretBytes(resolved.encode("utf-8"))


def _development_capabilities() -> ProductionFeatureCapabilities:
    return ProductionFeatureCapabilities(
        whatsapp_enabled=True,
        crm_enabled=True,
        notifications_enabled=True,
        media_scanning_enabled=True,
        external_ai_enabled=_bool_env("AI_EXTERNAL_CALLS_ENABLED", default=False),
    )


def _production_media_access_token_resolver(
    credential_resolver: EnvWhatsAppCredentialResolver,
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
) -> Callable[[uuid.UUID, uuid.UUID, uuid.UUID], object]:
    async def resolve(
        tenant_id: uuid.UUID,
        channel_connection_id: uuid.UUID,
        media_reference_id: uuid.UUID,
    ) -> SecretBytes | None:
        _ = media_reference_id
        uow = integrated_uow_factory()
        async with uow:
            records = await uow.whatsapp_cloud_connections.list_by_tenant(tenant_id=tenant_id)
        match = next(
            (record for record in records if record.channel_connection_id == channel_connection_id),
            None,
        )
        if match is None or match.access_token_ref is None:
            return None
        return await credential_resolver.resolve_access_token(
            tenant_id=tenant_id,
            whatsapp_connection_id=match.id,
            reference_key=match.access_token_ref,
        )

    return resolve


def build_worker_runtime(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None = None,
) -> WorkerRuntime:
    override_values = _merge_managed_worker_overrides(settings, overrides)

    adapter_registry: ProviderAdapterRegistry
    pending_adapter_registry: ProviderAdapterRegistry | None = override_values.adapter_registry
    if settings.is_managed:
        if overrides is not None:
            if settings.is_production:
                key_provider = cast(
                    KeyProvider,
                    require_production_key_provider(override_values.key_provider),
                )
            else:
                if override_values.key_provider is None:
                    raise WorkerConfigurationError("staging worker key provider is required")
                key_provider = override_values.key_provider
            require_notification_transport_configured(app_env=settings.app_env)
            adapter_registry = require_production_provider_adapters(pending_adapter_registry)
        else:
            if override_values.key_provider is None or pending_adapter_registry is None:
                raise WorkerConfigurationError("managed worker runtime is incomplete")
            key_provider = override_values.key_provider
            adapter_registry = pending_adapter_registry
    else:
        key_provider = override_values.key_provider or _development_key_provider()
        if pending_adapter_registry is None:
            engine_for_adapters = override_values.engine
            session_factory_for_adapters = override_values.session_factory
            if session_factory_for_adapters is None:
                if engine_for_adapters is None:
                    engine_for_adapters = create_authentication_engine(
                        normalize_database_url(settings.database_url)
                    )
                session_factory_for_adapters = create_authentication_sessionmaker(
                    engine_for_adapters
                )

            def dev_integrated_uow_factory() -> SqlAlchemyIntegratedUnitOfWork:
                return SqlAlchemyIntegratedUnitOfWork(session_factory_for_adapters)

            if os.environ.get("WHATSAPP_APP_SECRET_REF", "").strip():
                adapter_registry = _build_development_adapter_registry(
                    integrated_uow_factory=dev_integrated_uow_factory,
                    credential_resolver=EnvWhatsAppCredentialResolver(),
                )
            else:
                adapter_registry = _development_adapter_registry()
        else:
            adapter_registry = pending_adapter_registry

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

    capabilities = override_values.capabilities
    if capabilities is None:
        capabilities = (
            resolve_production_feature_capabilities()
            if settings.is_managed
            else _development_capabilities()
        )

    if override_values.content_encryption is not None:
        content_encryption = override_values.content_encryption
    else:
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

    if override_values.knowledge_search_key_provider is not None:
        knowledge_key_provider = override_values.knowledge_search_key_provider
    elif settings.is_development:
        knowledge_key_provider = DevKnowledgeSearchKeyProvider()
    else:
        raise WorkerConfigurationError("knowledge search key provider is required")

    whatsapp_credential_resolver = EnvWhatsAppCredentialResolver()
    messaging_policy = WhatsAppMessagingPolicy()
    disabled_handler = OptionalFeatureDisabledHandler()

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
        key_provider=knowledge_key_provider,
        service_actor_id=service_actor_id,
        uuid_factory=uuid.uuid4,
    )
    ai_clock = _WorkerAiClock()
    retrieval_service = KnowledgeRetrievalService(
        uow_factory=integrated_port_factory,
        key_provider=knowledge_key_provider,
        content_encryption=content_encryption,
        uuid_factory=uuid.uuid4,
    )

    ai_providers: dict[AiProviderCode, AiProvider] = {
        AiProviderCode.SYNTHETIC: SyntheticAiProvider(),
    }
    if capabilities.external_ai_enabled or settings.is_development:
        ai_providers[AiProviderCode.OPENAI_COMPATIBLE] = OpenAICompatibleChatAdapter(
            base_url=_deepseek_base_url(),
            provider_code=AiProviderCode.OPENAI_COMPATIBLE,
        )

    external_calls_enabled = (
        capabilities.external_ai_enabled
        if settings.is_managed
        else _bool_env("AI_EXTERNAL_CALLS_ENABLED", default=False)
    )
    ai_gateway = NopqAiGateway(
        external_calls_enabled=external_calls_enabled,
        clock=ai_clock,
        input_gate=AiInputGate(),
        assembler=ConversationInputAssembler(),
        prompt_builder=AiPromptBuilder(),
        output_validator=AiOutputValidator(),
        budget_service=AiBudgetService(),
        provider_registry=_WorkerAiProviderRegistry(providers=ai_providers),
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
        provider_code=(
            AiProviderCode.OPENAI_COMPATIBLE
            if capabilities.external_ai_enabled
            else AiProviderCode.SYNTHETIC
        ),
        uuid_factory=uuid.uuid4,
        clock=ai_clock.now,
    )

    if capabilities.whatsapp_enabled:
        provider_message_send_handler: OutboxJobHandler = ProviderMessageSendHandler(
            uow_factory=integrated_port_factory,
            content_encryption=content_encryption,
            credential_resolver=whatsapp_credential_resolver,
            messaging_policy=messaging_policy,
            service_actor_id=service_actor_id,
            uuid_factory=uuid.uuid4,
        )
        provider_templates_sync_handler: OutboxJobHandler = ProviderTemplatesSyncHandler(
            uow_factory=integrated_port_factory,
            credential_resolver=whatsapp_credential_resolver,
            service_actor_id=service_actor_id,
            uuid_factory=uuid.uuid4,
            clock=ai_clock.now,
        )
        media_access_token_resolver = (
            _production_media_access_token_resolver(
                whatsapp_credential_resolver,
                integrated_uow_factory=integrated_uow_factory,
            )
            if settings.is_managed
            else _development_media_access_token_resolver
        )
        media_fetch_handler: OutboxJobHandler = MediaFetchHandler(
            uow_factory=integrated_port_factory,
            media_fetcher=WhatsAppMediaFetchAdapter(
                graph_api_base_url=f"https://graph.facebook.com/{_whatsapp_graph_api_version()}",
            ),
            access_token_resolver=media_access_token_resolver,
            content_encryption=content_encryption,
            uuid_factory=uuid.uuid4,
        )
    else:
        provider_message_send_handler = disabled_handler
        provider_templates_sync_handler = disabled_handler
        media_fetch_handler = disabled_handler

    secret_resolver = override_values.secret_resolver or EnvSecretResolver()
    notification_delivery_service = NotificationDeliveryService(
        uow_factory=integrated_port_factory,
        uuid_factory=uuid.uuid4,
        content_encryption=content_encryption,
        verification_base_url=os.environ.get(
            "AUTH_VERIFICATION_BASE_URL",
            "http://127.0.0.1:3000/verify",
        ),
        reset_base_url=os.environ.get(
            "AUTH_PASSWORD_RESET_BASE_URL",
            "http://127.0.0.1:3000/reset",
        ),
        service_actor_id=service_actor_id,
    )
    notification_sender = build_notification_sender_sync(
        app_env=settings.app_env,
        secret_resolver=secret_resolver,
    )
    notification_deliver_handler = NotificationDeliverHandler(
        uow_factory=integrated_port_factory,
        delivery_service=notification_delivery_service,
        sender=notification_sender,
        service_actor_id=service_actor_id,
    )
    legal_hold_service = LegalHoldService(
        uow_factory=integrated_port_factory,
        uuid_factory=uuid.uuid4,
    )
    retention_purge_handler = RetentionPurgeHandler(
        uow_factory=integrated_port_factory,
        uuid_factory=uuid.uuid4,
        legal_hold_service=legal_hold_service,
        clock=ai_clock,
    )

    if capabilities.media_scanning_enabled:
        media_scanner = override_values.media_scanner or ClamAvScannerAdapter(
            host=os.environ.get("CLAMAV_HOST", "127.0.0.1"),
            port=int(os.environ.get("CLAMAV_PORT", "3310")),
        )
        media_scan_handler: OutboxJobHandler = MediaScanHandler(
            uow_factory=integrated_port_factory,
            media_scanner=media_scanner,
            content_encryption=content_encryption,
            service_actor_id=service_actor_id,
            uuid_factory=uuid.uuid4,
        )
    else:
        media_scan_handler = disabled_handler

    crm_credential_resolver = EnvCrmCredentialResolver()
    crm_adapters: dict[CrmProviderCode, CrmAdapter] = (
        {CrmProviderCode.BITRIX24: Bitrix24Adapter()} if capabilities.crm_enabled else {}
    )
    crm_sync_service = CrmSyncService(
        uow_factory=integrated_port_factory,
        credential_resolver=crm_credential_resolver,
        adapters=crm_adapters,
        uuid_factory=uuid.uuid4,
        clock=ai_clock.now,
    )
    crm_sync_handler: OutboxJobHandler = (
        CrmSyncHandler(sync_service=crm_sync_service)
        if capabilities.crm_enabled
        else disabled_handler
    )

    handlers: dict[OutboxJobKind, OutboxJobHandler] = {
        OutboxJobKind.WEBHOOK_NORMALIZE: webhook_handler,
        OutboxJobKind.CSV_IMPORT: csv_import_handler,
        OutboxJobKind.CONTENT_REDACT: content_redact_handler,
        OutboxJobKind.METRICS_RECALCULATE: metrics_recalculate_handler,
        OutboxJobKind.KNOWLEDGE_INDEX: knowledge_index_handler,
        OutboxJobKind.MESSAGE_ANALYZE: message_analyze_handler,
        OutboxJobKind.PROVIDER_MESSAGE_SEND: provider_message_send_handler,
        OutboxJobKind.PROVIDER_TEMPLATES_SYNC: provider_templates_sync_handler,
        OutboxJobKind.NOTIFICATION_DELIVER: notification_deliver_handler,
        OutboxJobKind.RETENTION_DELETE: retention_purge_handler,
        OutboxJobKind.MEDIA_FETCH: media_fetch_handler,
        OutboxJobKind.MEDIA_SCAN: media_scan_handler,
        OutboxJobKind.CRM_SYNC: crm_sync_handler,
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

    def publisher_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxPublisherService:
        return OutboxPublisherService(
            outbox_jobs=uow.outbox_jobs,
            outbox_job_attempts=uow.outbox_job_attempts,
            queue_publisher=queue_publisher,
            worker_id=settings.worker_id,
        )

    def processor_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxProcessorService:
        return OutboxProcessorService(
            outbox_jobs=uow.outbox_jobs,
            outbox_job_attempts=uow.outbox_job_attempts,
            handlers=handlers,
            worker_id=settings.worker_id,
            supported_job_kinds=XY_SUPPORTED_JOB_KINDS,
            clock=ai_clock,
        )

    def reconciliation_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxReconciliationService:
        return OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)

    def whatsapp_reconciliation_service_factory() -> WhatsAppReconciliationService:
        return WhatsAppReconciliationService(
            uow_factory=integrated_port_factory,
            uuid_factory=uuid.uuid4,
            clock=ai_clock.now,
            service_actor_id=service_actor_id,
        )

    def crm_reconciliation_service_factory() -> CrmReconciliationService:
        return CrmReconciliationService(
            uow_factory=integrated_port_factory,
            sync_service=crm_sync_service,
        )

    def retention_purge_service_factory() -> RetentionPurgeService:
        return RetentionPurgeService(
            uow_factory=integrated_port_factory,
            uuid_factory=uuid.uuid4,
            legal_hold_service=legal_hold_service,
        )

    def kms_rewrap_service_factory() -> KmsRewrapService:
        return KmsRewrapService(
            uow_factory=integrated_port_factory,
            content_encryption=content_encryption,
            service_actor_id=service_actor_id,
        )

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
        whatsapp_reconciliation_service_factory=whatsapp_reconciliation_service_factory,
        crm_reconciliation_service_factory=crm_reconciliation_service_factory,
        retention_purge_service_factory=retention_purge_service_factory,
        kms_rewrap_service_factory=kms_rewrap_service_factory,
        handlers=handlers,
        capabilities=capabilities,
    )
