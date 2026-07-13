"""Environment-driven production composition helpers shared by API and worker."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.encryption_ports import KeyProvider, RetentionExpiryCalculator
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider
from closeros.application.privileged_mfa_requirement_policy import (
    PrivilegedMembershipMfaRequirementPolicy,
)
from closeros.application.provider_adapter_registry import ProviderAdapterRegistry
from closeros.application.provider_ports import ImportContentScanner, WhatsAppCredentialResolver
from closeros.application.secret_ports import SecretResolver
from closeros.domain.knowledge import SEARCH_KEY_VERSION
from closeros.domain.provider_credentials import SecretBytes
from closeros.infrastructure.aes_gcm_encryption import AesGcmContentCryptography
from closeros.infrastructure.clamav_scanner_adapter import ClamAvScannerAdapter
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.env_knowledge_search_key_provider import (
    EnvKnowledgeSearchKeyProvider,
)
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver
from closeros.infrastructure.env_whatsapp_credential_resolver import (
    EnvWhatsAppCredentialResolver,
)
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.noop_import_content_scanner import NoOpImportContentScanner
from closeros.infrastructure.production_feature_capabilities import (
    ProductionFeatureCapabilities,
    resolve_production_feature_capabilities,
)
from closeros.infrastructure.redis_distributed_rate_limiter import RedisDistributedRateLimiter
from closeros.infrastructure.remote_kms_key_provider import RemoteKmsKeyProvider
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import require_production_key_provider
from closeros.infrastructure.totp_mfa_verifier import DatabaseTotpMfaVerifier
from closeros.infrastructure.whatsapp_cloud_adapter import WhatsAppCloudWebhookAdapter


class ProductionConfigurationError(RuntimeError):
    """Raised when required production configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ProductionSharedRuntime:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork]
    key_provider: KeyProvider
    secret_resolver: SecretResolver
    content_encryption: ContentEncryptionService
    redis: Redis
    rate_limiter: RedisDistributedRateLimiter
    capabilities: ProductionFeatureCapabilities
    knowledge_search_key_provider: KnowledgeSearchKeyProvider


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ProductionConfigurationError(f"{name} is not set")
    return value


def _is_feature_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_remote_kms_from_env(
    *, secret_resolver: SecretResolver | None = None
) -> RemoteKmsKeyProvider:
    base_url = _require_env("KMS_BASE_URL")
    token_ref = _require_env("KMS_API_TOKEN_REF")
    active_version = _require_env("KMS_ACTIVE_KEY_VERSION")
    versions_raw = _require_env("KMS_KEY_VERSIONS")
    versions = tuple(part.strip() for part in versions_raw.split(",") if part.strip())
    if not versions:
        raise ProductionConfigurationError("KMS_KEY_VERSIONS must list at least one version")
    return RemoteKmsKeyProvider(
        base_url=base_url,
        api_token_reference=token_ref,
        active_key_version=active_version,
        key_versions=versions,
        _token_resolver=secret_resolver,
    )


def build_production_redis_from_env() -> tuple[Redis, RedisDistributedRateLimiter]:
    redis_url = _require_env("REDIS_URL")
    hmac_secret = _require_env("REDIS_RATE_LIMIT_HMAC_SECRET").encode("utf-8")
    redis = Redis.from_url(redis_url, decode_responses=False)
    return redis, RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)


def build_production_content_encryption(
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
    key_provider: KeyProvider,
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=key_provider,
            secure_random=OsSecureRandom(),
        ),
        retention_expiry_calculator=RetentionExpiryCalculator(),
        uow_factory=cast(Callable[[], IntegratedUnitOfWork], integrated_uow_factory),
    )


def build_production_mfa_verifier(
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
    content_encryption: ContentEncryptionService,
    service_actor_id: UUID,
    uuid_factory: Callable[[], UUID],
) -> DatabaseTotpMfaVerifier:
    return DatabaseTotpMfaVerifier(
        uow_factory=cast(Callable[[], IntegratedUnitOfWork], integrated_uow_factory),
        content_encryption=content_encryption,
        service_actor_id=service_actor_id,
        uuid_factory=uuid_factory,
    )


def build_production_mfa_policy(
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
) -> PrivilegedMembershipMfaRequirementPolicy:
    return PrivilegedMembershipMfaRequirementPolicy(
        uow_factory=cast(Callable[[], IntegratedUnitOfWork], integrated_uow_factory),
    )


def _whatsapp_graph_api_version() -> str:
    raw_value = os.environ.get("WHATSAPP_GRAPH_API_VERSION", "v21.0").strip()
    return raw_value or "v21.0"


def build_production_adapter_registry(
    *,
    integrated_uow_factory: Callable[[], SqlAlchemyIntegratedUnitOfWork],
    credential_resolver: WhatsAppCredentialResolver | None = None,
    capabilities: ProductionFeatureCapabilities | None = None,
) -> ProviderAdapterRegistry:
    resolved = capabilities or resolve_production_feature_capabilities()
    if not resolved.whatsapp_enabled:
        return ProviderAdapterRegistry(adapters=())

    resolver = credential_resolver or EnvWhatsAppCredentialResolver()
    if not os.environ.get("WHATSAPP_APP_SECRET_REF", "").strip():
        raise ProductionConfigurationError("WHATSAPP_ENABLED requires WHATSAPP_APP_SECRET_REF")

    async def resolve_app_secret_for_channel(
        tenant_id: UUID,
        channel_connection_id: UUID,
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
        return await resolver.resolve_app_secret(
            tenant_id=tenant_id,
            whatsapp_connection_id=match.id,
            reference_key=match.app_secret_ref,
        )

    adapters: list[object] = [
        WhatsAppCloudWebhookAdapter(
            resolve_app_secret_for_channel=resolve_app_secret_for_channel,
            graph_api_version=_whatsapp_graph_api_version(),
        ),
    ]
    return ProviderAdapterRegistry(adapters=tuple(adapters))  # type: ignore[arg-type]


def build_production_import_scanner(
    *,
    capabilities: ProductionFeatureCapabilities | None = None,
) -> ImportContentScanner:
    resolved = capabilities or resolve_production_feature_capabilities()
    if not resolved.media_scanning_enabled:
        return NoOpImportContentScanner()
    host = _require_env("CLAMAV_HOST")
    port = int(_require_env("CLAMAV_PORT"))
    return cast(ImportContentScanner, ClamAvScannerAdapter(host=host, port=port))


def build_production_media_scanner(
    *,
    capabilities: ProductionFeatureCapabilities | None = None,
) -> ClamAvScannerAdapter | None:
    resolved = capabilities or resolve_production_feature_capabilities()
    if not resolved.media_scanning_enabled:
        return None
    host = _require_env("CLAMAV_HOST")
    port = int(_require_env("CLAMAV_PORT"))
    return ClamAvScannerAdapter(host=host, port=port)


def build_production_knowledge_search_key_provider(
    *,
    secret_resolver: SecretResolver | None = None,
) -> EnvKnowledgeSearchKeyProvider:
    reference = _require_env("KNOWLEDGE_SEARCH_KEY_REF")
    version = os.environ.get("KNOWLEDGE_SEARCH_KEY_VERSION", SEARCH_KEY_VERSION).strip()
    return EnvKnowledgeSearchKeyProvider(
        secret_reference=reference,
        search_key_version=version or SEARCH_KEY_VERSION,
        _secret_resolver=secret_resolver,
    )


def validate_optional_production_features(
    *,
    capabilities: ProductionFeatureCapabilities,
) -> None:
    if capabilities.whatsapp_enabled and not os.environ.get("WHATSAPP_APP_SECRET_REF", "").strip():
        raise ProductionConfigurationError("WHATSAPP_ENABLED requires WHATSAPP_APP_SECRET_REF")
    if capabilities.crm_enabled:
        for name in ("BITRIX24_PORTAL_DOMAIN", "BITRIX24_ACCESS_TOKEN_REF"):
            if not os.environ.get(name, "").strip():
                raise ProductionConfigurationError(f"CRM_ENABLED requires {name}")
    if capabilities.media_scanning_enabled:
        for name in ("CLAMAV_HOST", "CLAMAV_PORT"):
            if not os.environ.get(name, "").strip():
                raise ProductionConfigurationError(f"media scanning enabled requires {name}")
    if capabilities.notifications_enabled:
        for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM_ADDRESS"):
            if not os.environ.get(name, "").strip():
                raise ProductionConfigurationError(f"NOTIFICATIONS_ENABLED requires {name}")
    if capabilities.external_ai_enabled:
        if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
            raise ProductionConfigurationError(
                "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_API_KEY"
            )
        if not (
            os.environ.get("DEEPSEEK_MODEL", "").strip() or os.environ.get("AI_MODEL", "").strip()
        ):
            raise ProductionConfigurationError("AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_MODEL")


def build_production_shared_runtime(
    *,
    database_url: str,
    ingestion_service_id: UUID,
) -> ProductionSharedRuntime:
    _ = ingestion_service_id
    capabilities = resolve_production_feature_capabilities()
    validate_optional_production_features(capabilities=capabilities)

    engine = create_authentication_engine(normalize_database_url(database_url))
    session_factory = create_authentication_sessionmaker(engine)

    def integrated_uow_factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(session_factory)

    secret_resolver = EnvSecretResolver()
    key_provider = cast(
        KeyProvider,
        require_production_key_provider(build_remote_kms_from_env(secret_resolver=secret_resolver)),
    )
    content_encryption = build_production_content_encryption(
        integrated_uow_factory=integrated_uow_factory,
        key_provider=key_provider,
    )
    redis, rate_limiter = build_production_redis_from_env()
    knowledge_search_key_provider = build_production_knowledge_search_key_provider(
        secret_resolver=secret_resolver,
    )
    return ProductionSharedRuntime(
        engine=engine,
        session_factory=session_factory,
        integrated_uow_factory=integrated_uow_factory,
        key_provider=key_provider,
        secret_resolver=secret_resolver,
        content_encryption=content_encryption,
        redis=redis,
        rate_limiter=rate_limiter,
        capabilities=capabilities,
        knowledge_search_key_provider=knowledge_search_key_provider,
    )


def require_crm_configured(
    *,
    capabilities: ProductionFeatureCapabilities | None = None,
) -> None:
    resolved = capabilities or resolve_production_feature_capabilities()
    if not resolved.crm_enabled:
        return
    for name in ("BITRIX24_PORTAL_DOMAIN", "BITRIX24_ACCESS_TOKEN_REF"):
        if not os.environ.get(name, "").strip():
            raise ProductionConfigurationError(f"CRM_ENABLED requires {name}")


__all__ = [
    "ProductionConfigurationError",
    "ProductionSharedRuntime",
    "build_production_adapter_registry",
    "build_production_content_encryption",
    "build_production_import_scanner",
    "build_production_knowledge_search_key_provider",
    "build_production_media_scanner",
    "build_production_mfa_policy",
    "build_production_mfa_verifier",
    "build_production_redis_from_env",
    "build_production_shared_runtime",
    "build_remote_kms_from_env",
    "require_crm_configured",
    "validate_optional_production_features",
]
