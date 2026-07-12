"""API runtime composition and dependency container."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from closeros.application.atomic_content_commands import AtomicContentCommandService
from closeros.application.audit_persistence import AuditUnitOfWork
from closeros.application.audit_queries import TenantAuditQueryService
from closeros.application.authentication_persistence import AuthenticationUnitOfWork
from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    MfaRequirementPolicy,
    MfaVerifier,
)
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.csv_import_service import CsvImportService
from closeros.application.encryption_ports import RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.password_hashing import PasswordHasher
from closeros.application.platform_unit_of_work import PlatformUnitOfWork
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.provider_ports import ImportContentScanner, WebhookRateLimiter
from closeros.application.tenant_context import TenantContextResolver, TenantListingService
from closeros.application.tenant_persistence import TenantUnitOfWork
from closeros.application.webhook_ingestion import WebhookIngestionService
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork
from closeros.infrastructure.authentication_unit_of_work import SqlAlchemyAuthenticationUnitOfWork
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.in_memory_webhook_rate_limiter import InMemoryWebhookRateLimiter
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.noop_import_content_scanner import NoOpImportContentScanner
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import (
    StaticKeyProvider,
    require_production_key_provider,
)
from closeros.infrastructure.synthetic_hmac_adapter import SyntheticHmacWebhookAdapter
from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from closeros_api.auth_ports import (
    AcceptingMfaVerifier,
    CaptureNotificationDispatcher,
    Clock,
    ConfigurableMfaRequirementPolicy,
    InMemoryRateLimiter,
    NotificationDispatcher,
    RandomUuidFactory,
    RateLimiter,
    SystemClock,
    UuidFactory,
)
from closeros_api.auth_security import SessionCookieConfig, session_cookie_config
from closeros_api.settings import ApiSettings

_DEV_KEK_V1 = bytes(range(32))
_DEV_KEY_VERSION = "dev-kek-v1"


class ProductionProviderAdaptersRequiredError(RuntimeError):
    """Raised when production composition lacks explicit provider adapters."""


class ProductionImportContentScannerRequiredError(RuntimeError):
    """Raised when production composition lacks an explicit CSV content scanner."""


class ProductionWebhookRateLimiterRequiredError(RuntimeError):
    """Raised when production composition lacks an explicit webhook rate limiter."""


def require_production_provider_adapters(
    registry: ProviderAdapterRegistry | None,
) -> ProviderAdapterRegistry:
    if registry is None:
        raise ProductionProviderAdaptersRequiredError(
            "production requires explicit provider adapter registry injection"
        )
    return registry


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


def _build_content_encryption_service(
    *,
    uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
    key_provider: StaticKeyProvider,
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=key_provider,
            secure_random=OsSecureRandom(),
        ),
        retention_expiry_calculator=RetentionExpiryCalculator(),
        uow_factory=cast(Callable[[], IntegratedUnitOfWork], uow_factory),
    )


@dataclass
class ApiRuntimeOverrides:
    workflow_service: AuthenticationWorkflowService | None = None
    uow_factory: Callable[[], AuthenticationUnitOfWork] | None = None
    platform_uow_factory: Callable[[], PlatformUnitOfWork] | None = None
    tenant_uow_factory: Callable[[], TenantUnitOfWork] | None = None
    audit_uow_factory: Callable[[], AuditUnitOfWork] | None = None
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork] | None = None
    tenant_context_resolver: TenantContextResolver | None = None
    tenant_listing_service: TenantListingService | None = None
    tenant_audit_query_service: TenantAuditQueryService | None = None
    password_hasher: PasswordHasher | None = None
    clock: Clock | None = None
    uuid_factory: UuidFactory | None = None
    mfa_requirement_policy: MfaRequirementPolicy | None = None
    mfa_verifier: MfaVerifier | None = None
    notification_dispatcher: NotificationDispatcher | None = None
    rate_limiter: RateLimiter | None = None
    key_provider: StaticKeyProvider | None = None
    adapter_registry: ProviderAdapterRegistry | None = None
    webhook_rate_limiter: WebhookRateLimiter | None = None
    content_scanner: ImportContentScanner | None = None
    content_encryption: ContentEncryptionService | None = None
    atomic_content_commands: AtomicContentCommandService | None = None
    webhook_ingestion: WebhookIngestionService | None = None
    csv_import_service: CsvImportService | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None


AuthRuntimeOverrides = ApiRuntimeOverrides


@dataclass
class ApiRuntime:
    settings: ApiSettings
    workflows: AuthenticationWorkflowService
    password_hasher: PasswordHasher
    clock: Clock
    uuid_factory: UuidFactory
    mfa_requirement_policy: MfaRequirementPolicy
    mfa_verifier: MfaVerifier
    notification_dispatcher: NotificationDispatcher
    rate_limiter: RateLimiter
    cookie_config: SessionCookieConfig
    engine: AsyncEngine | None
    session_factory: async_sessionmaker[AsyncSession] | None
    platform_uow_factory: Callable[[], PlatformUnitOfWork] | None
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork] | None
    tenant_context_resolver: TenantContextResolver
    tenant_listing_service: TenantListingService
    tenant_audit_query_service: TenantAuditQueryService
    content_encryption: ContentEncryptionService
    atomic_content_commands: AtomicContentCommandService
    adapter_registry: ProviderAdapterRegistry
    webhook_ingestion: WebhookIngestionService
    csv_import_service: CsvImportService

    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


AuthRuntime = ApiRuntime


class _UnconfiguredTenantContextResolver:
    async def resolve(self, **kwargs: object) -> object:
        raise RuntimeError("tenant context resolver is not configured")


class _UnconfiguredTenantListingService:
    async def list_tenants_for_user(self, **kwargs: object) -> tuple[tuple[object, object], ...]:
        raise RuntimeError("tenant listing service is not configured")


class _UnconfiguredTenantAuditQueryService:
    async def query(self, **kwargs: object) -> object:
        raise RuntimeError("tenant audit query service is not configured")


class _UnconfiguredWebhookIngestion:
    async def accept_provider_webhook(self, **kwargs: object) -> object:
        raise RuntimeError("webhook ingestion is not configured")


class _UnconfiguredCsvImportService:
    async def preview_upload(self, **kwargs: object) -> object:
        raise RuntimeError("csv import service is not configured")

    async def start_import(self, **kwargs: object) -> object:
        raise RuntimeError("csv import service is not configured")

    async def cancel_import(self, **kwargs: object) -> object:
        raise RuntimeError("csv import service is not configured")

    async def get_status(self, **kwargs: object) -> object:
        raise RuntimeError("csv import service is not configured")


class _UnconfiguredContentEncryption:
    data_key_cryptography: object = object()

    async def encrypt_and_persist(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("content encryption is not configured")


class _UnconfiguredAtomicContentCommands:
    async def accept_webhook(self, **kwargs: object) -> object:
        raise RuntimeError("atomic content commands are not configured")


def build_api_runtime(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None = None,
) -> ApiRuntime:
    override_values = overrides or ApiRuntimeOverrides()
    settings.validate_for_runtime()

    engine = override_values.engine
    session_factory = override_values.session_factory
    if override_values.workflow_service is None and session_factory is None:
        if engine is None:
            engine = create_authentication_engine(normalize_database_url(settings.database_url))
        session_factory = create_authentication_sessionmaker(engine)

    resolved_uow_factory = override_values.uow_factory
    password_hasher = override_values.password_hasher or Argon2idPasswordHasher()
    clock = override_values.clock or SystemClock()
    uuid_factory = override_values.uuid_factory or RandomUuidFactory()

    if settings.is_production:
        if override_values.mfa_requirement_policy is None:
            raise RuntimeError("production MFA requirement policy must be configured explicitly")
        if override_values.notification_dispatcher is None:
            raise RuntimeError("production notification dispatcher must be configured explicitly")
        if override_values.rate_limiter is None:
            raise RuntimeError("production rate limiter must be configured explicitly")
        mfa_policy = override_values.mfa_requirement_policy
        mfa_verifier = override_values.mfa_verifier or AcceptingMfaVerifier()
        dispatcher = override_values.notification_dispatcher
        rate_limiter = override_values.rate_limiter
        key_provider = cast(
            StaticKeyProvider,
            require_production_key_provider(override_values.key_provider),
        )
        adapter_registry = require_production_provider_adapters(override_values.adapter_registry)
        if override_values.webhook_rate_limiter is None:
            raise ProductionWebhookRateLimiterRequiredError(
                "production webhook rate limiter must be configured explicitly"
            )
        webhook_rate_limiter = override_values.webhook_rate_limiter
        if override_values.content_scanner is None:
            raise ProductionImportContentScannerRequiredError(
                "production CSV content scanner must be configured explicitly"
            )
        content_scanner = override_values.content_scanner
    else:
        mfa_policy = override_values.mfa_requirement_policy or ConfigurableMfaRequirementPolicy()
        mfa_verifier = override_values.mfa_verifier or AcceptingMfaVerifier()
        dispatcher = override_values.notification_dispatcher or CaptureNotificationDispatcher()
        rate_limiter = override_values.rate_limiter or InMemoryRateLimiter()
        key_provider = override_values.key_provider or _development_key_provider()
        adapter_registry = override_values.adapter_registry or _development_adapter_registry()
        webhook_rate_limiter = override_values.webhook_rate_limiter or InMemoryWebhookRateLimiter()
        content_scanner = override_values.content_scanner or NoOpImportContentScanner()

    if override_values.workflow_service is None:
        if resolved_uow_factory is None:
            if session_factory is None:
                raise RuntimeError("session factory is required to build the unit of work")

            def resolved_uow_factory() -> AuthenticationUnitOfWork:
                return cast(
                    AuthenticationUnitOfWork,
                    SqlAlchemyAuthenticationUnitOfWork(session_factory),
                )

        workflows = AuthenticationWorkflowService(
            uow_factory=resolved_uow_factory,
            password_hasher=password_hasher,
            session_touch_interval=settings.session_touch_interval,
        )
    else:
        workflows = override_values.workflow_service

    platform_uow_factory = override_values.platform_uow_factory
    tenant_uow_factory = override_values.tenant_uow_factory
    audit_uow_factory = override_values.audit_uow_factory
    integrated_uow_factory = override_values.integrated_uow_factory

    if session_factory is not None:
        if platform_uow_factory is None:

            def platform_uow_factory() -> PlatformUnitOfWork:
                return cast(
                    PlatformUnitOfWork,
                    SqlAlchemyPlatformUnitOfWork(session_factory),
                )

        if tenant_uow_factory is None:

            def tenant_uow_factory() -> TenantUnitOfWork:
                return cast(
                    TenantUnitOfWork,
                    SqlAlchemyTenantUnitOfWork(session_factory),
                )

        if audit_uow_factory is None:

            def audit_uow_factory() -> AuditUnitOfWork:
                return cast(
                    AuditUnitOfWork,
                    SqlAlchemyAuditUnitOfWork(session_factory),
                )

        if integrated_uow_factory is None:

            def integrated_uow_factory() -> SqlAlchemyIntegratedUnitOfWork:
                return SqlAlchemyIntegratedUnitOfWork(session_factory)

    if integrated_uow_factory is not None:
        integrated_port_factory = cast(
            Callable[[], IntegratedUnitOfWork],
            integrated_uow_factory,
        )
        content_encryption = (
            override_values.content_encryption
            or _build_content_encryption_service(
                uow_factory=integrated_uow_factory,
                key_provider=key_provider,
            )
        )
        atomic_content_commands = (
            override_values.atomic_content_commands
            or AtomicContentCommandService(
                uow_factory=integrated_port_factory,
                content_encryption=content_encryption,
            )
        )
        webhook_ingestion = override_values.webhook_ingestion or WebhookIngestionService(
            uow_factory=integrated_port_factory,
            atomic_commands=atomic_content_commands,
            adapter_registry=adapter_registry,
            rate_limiter=webhook_rate_limiter,
            service_actor_id=settings.ingestion_service_id,
            uuid_factory=uuid_factory,
        )
        csv_import_service = override_values.csv_import_service or CsvImportService(
            uow_factory=integrated_port_factory,
            content_encryption=content_encryption,
            content_scanner=content_scanner,
            uuid_factory=uuid_factory,
        )
    else:
        content_encryption = cast(
            ContentEncryptionService,
            override_values.content_encryption or _UnconfiguredContentEncryption(),
        )
        atomic_content_commands = cast(
            AtomicContentCommandService,
            override_values.atomic_content_commands or _UnconfiguredAtomicContentCommands(),
        )
        webhook_ingestion = cast(
            WebhookIngestionService,
            override_values.webhook_ingestion or _UnconfiguredWebhookIngestion(),
        )
        csv_import_service = cast(
            CsvImportService,
            override_values.csv_import_service or _UnconfiguredCsvImportService(),
        )

    tenant_context_resolver = override_values.tenant_context_resolver
    if tenant_context_resolver is None:
        if platform_uow_factory is not None:
            tenant_context_resolver = TenantContextResolver(
                uow_factory=platform_uow_factory,
                session_touch_interval=settings.session_touch_interval,
            )
        else:
            tenant_context_resolver = cast(
                TenantContextResolver,
                _UnconfiguredTenantContextResolver(),
            )

    tenant_listing_service = override_values.tenant_listing_service
    if tenant_listing_service is None:
        if tenant_uow_factory is not None:
            tenant_listing_service = TenantListingService(uow_factory=tenant_uow_factory)
        else:
            tenant_listing_service = cast(
                TenantListingService,
                _UnconfiguredTenantListingService(),
            )

    tenant_audit_query_service = override_values.tenant_audit_query_service
    if tenant_audit_query_service is None:
        if audit_uow_factory is not None:
            tenant_audit_query_service = TenantAuditQueryService(
                audit_uow_factory=audit_uow_factory,
            )
        else:
            tenant_audit_query_service = cast(
                TenantAuditQueryService,
                _UnconfiguredTenantAuditQueryService(),
            )

    return ApiRuntime(
        settings=settings,
        workflows=workflows,
        password_hasher=password_hasher,
        clock=clock,
        uuid_factory=uuid_factory,
        mfa_requirement_policy=mfa_policy,
        mfa_verifier=mfa_verifier,
        notification_dispatcher=dispatcher,
        rate_limiter=rate_limiter,
        cookie_config=session_cookie_config(is_production=settings.is_production),
        engine=engine,
        session_factory=session_factory,
        platform_uow_factory=platform_uow_factory,
        integrated_uow_factory=integrated_uow_factory,
        tenant_context_resolver=tenant_context_resolver,
        tenant_listing_service=tenant_listing_service,
        tenant_audit_query_service=tenant_audit_query_service,
        content_encryption=content_encryption,
        atomic_content_commands=atomic_content_commands,
        adapter_registry=adapter_registry,
        webhook_ingestion=webhook_ingestion,
        csv_import_service=csv_import_service,
    )


def build_auth_runtime(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None = None,
) -> ApiRuntime:
    return build_api_runtime(settings, overrides)
