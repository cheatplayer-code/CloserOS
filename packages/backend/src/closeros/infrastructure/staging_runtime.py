"""Environment-driven shared runtime for managed staging.

Staging deliberately uses production-like network, authentication, rate-limit,
and optional-feature boundaries while allowing deployment-injected static keys.
Production remains remote-KMS-only and rejects static key providers.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.encryption_ports import KeyProvider
from closeros.application.knowledge_search_key import KnowledgeSearchKeyProvider
from closeros.application.secret_ports import SecretResolver
from closeros.domain.knowledge import SEARCH_KEY_VERSION
from closeros.infrastructure.configured_knowledge_search_key_provider import (
    ConfiguredKnowledgeSearchKeyProvider,
)
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.production_feature_capabilities import (
    ProductionFeatureCapabilities,
    resolve_production_feature_capabilities,
)
from closeros.infrastructure.production_runtime import (
    build_production_content_encryption,
    validate_optional_production_features,
)
from closeros.infrastructure.redis_distributed_rate_limiter import RedisDistributedRateLimiter
from closeros.infrastructure.static_key_provider import StaticKeyProvider

_STAGING_KEY_VERSION_DEFAULT = "staging-kek-v1"
_MIN_HMAC_SECRET_BYTES = 32
_HEX_KEY_CHARACTERS = 64


class StagingConfigurationError(RuntimeError):
    """Raised when managed staging configuration is missing or unsafe."""


@dataclass(frozen=True, slots=True)
class StagingSharedRuntime:
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
        raise StagingConfigurationError(f"{name} is not set")
    return value


def _require_hex_key(name: str) -> bytes:
    raw_value = _require_env(name)
    if len(raw_value) != _HEX_KEY_CHARACTERS:
        raise StagingConfigurationError(f"{name} must contain exactly 64 hexadecimal characters")
    try:
        key = bytes.fromhex(raw_value)
    except ValueError as error:
        raise StagingConfigurationError(
            f"{name} must contain exactly 64 hexadecimal characters"
        ) from error
    if len(key) != 32:
        raise StagingConfigurationError(f"{name} must decode to exactly 32 bytes")
    return key


def build_staging_key_provider_from_env() -> StaticKeyProvider:
    """Build a staging-only KEK provider from a sealed 32-byte hex value."""

    version = os.environ.get(
        "STAGING_ENCRYPTION_KEY_VERSION",
        _STAGING_KEY_VERSION_DEFAULT,
    ).strip()
    if not version:
        raise StagingConfigurationError("STAGING_ENCRYPTION_KEY_VERSION must not be empty")
    key = _require_hex_key("STAGING_ENCRYPTION_KEY_HEX")
    return StaticKeyProvider(keys_by_version={version: key}, active_version=version)


def build_staging_knowledge_search_key_provider_from_env() -> KnowledgeSearchKeyProvider:
    """Build the staging lexical-search key provider from sealed key material."""

    key = _require_hex_key("STAGING_KNOWLEDGE_SEARCH_KEY_HEX")
    version = os.environ.get("KNOWLEDGE_SEARCH_KEY_VERSION", SEARCH_KEY_VERSION).strip()
    if not version:
        raise StagingConfigurationError("KNOWLEDGE_SEARCH_KEY_VERSION must not be empty")
    return ConfiguredKnowledgeSearchKeyProvider(
        search_key_version=version,
        key=key,
    )


def build_staging_redis_from_env() -> tuple[Redis, RedisDistributedRateLimiter]:
    redis_url = _require_env("REDIS_URL")
    hmac_secret = _require_env("REDIS_RATE_LIMIT_HMAC_SECRET").encode("utf-8")
    if len(hmac_secret) < _MIN_HMAC_SECRET_BYTES:
        raise StagingConfigurationError(
            "REDIS_RATE_LIMIT_HMAC_SECRET must contain at least 32 bytes"
        )
    redis = Redis.from_url(redis_url, decode_responses=False)
    return redis, RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)


def build_staging_shared_runtime(*, database_url: str) -> StagingSharedRuntime:
    """Compose managed staging dependencies without weakening production KMS rules."""

    capabilities = resolve_production_feature_capabilities()
    validate_optional_production_features(capabilities=capabilities)

    engine = create_authentication_engine(normalize_database_url(database_url))
    session_factory = create_authentication_sessionmaker(engine)

    def integrated_uow_factory() -> SqlAlchemyIntegratedUnitOfWork:
        return SqlAlchemyIntegratedUnitOfWork(session_factory)

    key_provider = build_staging_key_provider_from_env()
    content_encryption = build_production_content_encryption(
        integrated_uow_factory=integrated_uow_factory,
        key_provider=key_provider,
    )
    redis, rate_limiter = build_staging_redis_from_env()
    secret_resolver = EnvSecretResolver()
    knowledge_search_key_provider = build_staging_knowledge_search_key_provider_from_env()

    return StagingSharedRuntime(
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


__all__ = [
    "StagingConfigurationError",
    "StagingSharedRuntime",
    "build_staging_key_provider_from_env",
    "build_staging_knowledge_search_key_provider_from_env",
    "build_staging_redis_from_env",
    "build_staging_shared_runtime",
]
