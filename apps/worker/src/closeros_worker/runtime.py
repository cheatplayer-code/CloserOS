"""Worker runtime composition for outbox ingestion processing."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.csv_import_processor import CsvImportProcessor
from closeros.application.encryption_ports import RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.outbox_processor import OutboxJobHandler, OutboxProcessorService
from closeros.application.outbox_publisher import OutboxPublisherService
from closeros.application.outbox_reconciliation import OutboxReconciliationService
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.webhook_normalize_handler import WebhookNormalizeHandler
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

JK_SUPPORTED_JOB_KINDS = frozenset(
    {
        OutboxJobKind.WEBHOOK_NORMALIZE,
        OutboxJobKind.CSV_IMPORT,
    }
)

_DEV_KEK_V1 = bytes(range(32))
_DEV_KEY_VERSION = "dev-kek-v1"


class ProductionProviderAdaptersRequiredError(RuntimeError):
    """Raised when production worker composition lacks explicit provider adapters."""


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
    handlers: dict[OutboxJobKind, OutboxJobHandler] = {
        OutboxJobKind.WEBHOOK_NORMALIZE: webhook_handler,
        OutboxJobKind.CSV_IMPORT: csv_import_handler,
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
            supported_job_kinds=JK_SUPPORTED_JOB_KINDS,
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
