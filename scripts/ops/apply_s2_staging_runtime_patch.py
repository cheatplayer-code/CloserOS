"""Apply explicit staging-runtime and worker lifecycle edits."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected 1 match, found {count}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


api = "apps/api/src/closeros_api/composition.py"
worker = "apps/worker/src/closeros_worker/runtime.py"
worker_main = "apps/worker/src/closeros_worker/__main__.py"
ops_encryption = "packages/backend/src/closeros/infrastructure/ops_encryption.py"

replace_once(
    api,
    '''from closeros.infrastructure.redis_rate_limiter import RedisWebhookRateLimiter
from closeros.infrastructure.secure_random import OsSecureRandom
''',
    '''from closeros.infrastructure.redis_rate_limiter import RedisWebhookRateLimiter
from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.staging_runtime import build_staging_shared_runtime
''',
    "import staging runtime",
)
replace_once(
    api,
    '''def _merge_production_api_overrides(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None,
) -> ApiRuntimeOverrides:
    base = overrides or ApiRuntimeOverrides()
    if not settings.is_production:
        return base
    if overrides is not None:
        return base

    shared = build_production_shared_runtime(
        database_url=settings.database_url,
        ingestion_service_id=settings.ingestion_service_id,
    )
''',
    '''def _merge_managed_api_overrides(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None,
) -> ApiRuntimeOverrides:
    base = overrides or ApiRuntimeOverrides()
    if not settings.is_managed:
        return base
    if overrides is not None:
        return base

    if settings.is_production:
        shared = build_production_shared_runtime(
            database_url=settings.database_url,
            ingestion_service_id=settings.ingestion_service_id,
        )
    else:
        shared = build_staging_shared_runtime(database_url=settings.database_url)
''',
    "select production or staging shared runtime",
)
replace_once(
    api,
    "    override_values = _merge_production_api_overrides(settings, overrides)\n",
    "    override_values = _merge_managed_api_overrides(settings, overrides)\n",
    "use managed API overrides",
)
replace_once(
    api,
    '''    capabilities: ProductionFeatureCapabilities | None = (
        resolve_production_feature_capabilities() if settings.is_production else None
    )
''',
    '''    capabilities: ProductionFeatureCapabilities | None = (
        resolve_production_feature_capabilities() if settings.is_managed else None
    )
''',
    "resolve capabilities for managed environments",
)
replace_once(
    api,
    '''    if settings.is_production:
        if override_values.mfa_requirement_policy is None:
            raise RuntimeError("production MFA requirement policy must be configured explicitly")
        mfa_policy = override_values.mfa_requirement_policy
        if override_values.mfa_verifier is None:
            raise RuntimeError("production MFA verifier must be configured explicitly")
        mfa_verifier = override_values.mfa_verifier
        if override_values.notification_dispatcher is None:
            dispatcher = NoOpNotificationDispatcher()
        else:
            dispatcher = override_values.notification_dispatcher
        if override_values.rate_limiter is None:
            distributed_rate_limiter = _production_redis_rate_limiter()
            rate_limiter = cast(RateLimiter, distributed_rate_limiter)
            webhook_rate_limiter = override_values.webhook_rate_limiter or distributed_rate_limiter
        else:
            rate_limiter = override_values.rate_limiter
            if override_values.webhook_rate_limiter is None:
                raise ProductionWebhookRateLimiterRequiredError(
                    "production webhook rate limiter must be configured explicitly"
                )
            webhook_rate_limiter = override_values.webhook_rate_limiter
        key_provider = cast(
            KeyProvider,
            require_production_key_provider(override_values.key_provider),
        )
        adapter_registry = require_production_provider_adapters(override_values.adapter_registry)
        if override_values.content_scanner is None:
            raise ProductionImportContentScannerRequiredError(
                "production CSV content scanner must be configured explicitly"
            )
        content_scanner = override_values.content_scanner
''',
    '''    if settings.is_managed:
        if override_values.mfa_requirement_policy is None:
            raise RuntimeError("managed MFA requirement policy must be configured explicitly")
        mfa_policy = override_values.mfa_requirement_policy
        if override_values.mfa_verifier is None:
            raise RuntimeError("managed MFA verifier must be configured explicitly")
        mfa_verifier = override_values.mfa_verifier
        if override_values.notification_dispatcher is None:
            dispatcher = NoOpNotificationDispatcher()
        else:
            dispatcher = override_values.notification_dispatcher
        if override_values.rate_limiter is None:
            distributed_rate_limiter = _production_redis_rate_limiter()
            rate_limiter = cast(RateLimiter, distributed_rate_limiter)
            webhook_rate_limiter = override_values.webhook_rate_limiter or distributed_rate_limiter
        else:
            rate_limiter = override_values.rate_limiter
            if override_values.webhook_rate_limiter is None:
                raise ProductionWebhookRateLimiterRequiredError(
                    "managed webhook rate limiter must be configured explicitly"
                )
            webhook_rate_limiter = override_values.webhook_rate_limiter
        if settings.is_production:
            key_provider = cast(
                KeyProvider,
                require_production_key_provider(override_values.key_provider),
            )
        else:
            if override_values.key_provider is None:
                raise RuntimeError("staging key provider must be configured explicitly")
            key_provider = override_values.key_provider
        adapter_registry = require_production_provider_adapters(override_values.adapter_registry)
        if override_values.content_scanner is None:
            raise ProductionImportContentScannerRequiredError(
                "managed CSV content scanner must be configured explicitly"
            )
        content_scanner = override_values.content_scanner
''',
    "apply managed security dependencies",
)
replace_once(
    api,
    "    if not settings.is_production and dev_adapter_registry is None:\n",
    "    if settings.is_development and dev_adapter_registry is None:\n",
    "keep development adapters out of staging",
)
replace_once(
    api,
    "    if settings.is_production and capabilities is not None:\n",
    "    if settings.is_managed and capabilities is not None:\n",
    "use managed readiness probe",
)
replace_once(
    api,
    "        cookie_config=session_cookie_config(is_production=settings.is_production),\n",
    "        cookie_config=session_cookie_config(is_production=settings.is_managed),\n",
    "secure staging session cookie",
)

replace_once(
    worker,
    '''from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.static_key_provider import (
''',
    '''from closeros.infrastructure.secure_random import OsSecureRandom
from closeros.infrastructure.staging_runtime import build_staging_shared_runtime
from closeros.infrastructure.static_key_provider import (
''',
    "import staging worker runtime",
)
replace_once(
    worker,
    '''    publisher_service_factory: Callable[[], OutboxPublisherService]
    processor_service_factory: Callable[[], OutboxProcessorService]
    reconciliation_service_factory: Callable[[], OutboxReconciliationService]
''',
    '''    publisher_service_factory: Callable[
        [SqlAlchemyIntegratedUnitOfWork], OutboxPublisherService
    ]
    processor_service_factory: Callable[
        [SqlAlchemyIntegratedUnitOfWork], OutboxProcessorService
    ]
    reconciliation_service_factory: Callable[
        [SqlAlchemyIntegratedUnitOfWork], OutboxReconciliationService
    ]
''',
    "type active UoW worker factories",
)
replace_once(
    worker,
    '''def _merge_production_worker_overrides(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None,
) -> WorkerRuntimeOverrides:
    base = overrides or WorkerRuntimeOverrides()
    if not settings.is_production:
        return base
    if overrides is not None:
        return base

    service_actor_id = _ingestion_service_id(settings, base.ingestion_service_id)
    shared = build_production_shared_runtime(
        database_url=settings.database_url,
        ingestion_service_id=service_actor_id,
    )
''',
    '''def _merge_managed_worker_overrides(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None,
) -> WorkerRuntimeOverrides:
    base = overrides or WorkerRuntimeOverrides()
    if not settings.is_managed:
        return base
    if overrides is not None:
        return base

    service_actor_id = _ingestion_service_id(settings, base.ingestion_service_id)
    if settings.is_production:
        shared = build_production_shared_runtime(
            database_url=settings.database_url,
            ingestion_service_id=service_actor_id,
        )
    else:
        shared = build_staging_shared_runtime(database_url=settings.database_url)
''',
    "select production or staging worker runtime",
)
replace_once(
    worker,
    "    override_values = _merge_production_worker_overrides(settings, overrides)\n",
    "    override_values = _merge_managed_worker_overrides(settings, overrides)\n",
    "use managed worker overrides",
)
replace_once(
    worker,
    '''    if settings.is_production:
        if overrides is not None:
            key_provider = cast(
                KeyProvider,
                require_production_key_provider(override_values.key_provider),
            )
            require_notification_transport_configured(app_env=settings.app_env)
            adapter_registry = require_production_provider_adapters(pending_adapter_registry)
        else:
            if override_values.key_provider is None or pending_adapter_registry is None:
                raise WorkerConfigurationError("production worker runtime is incomplete")
            key_provider = override_values.key_provider
            adapter_registry = pending_adapter_registry
''',
    '''    if settings.is_managed:
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
''',
    "apply managed worker dependencies",
)
replace_once(
    worker,
    '''        capabilities = (
            resolve_production_feature_capabilities()
            if settings.is_production
            else _development_capabilities()
        )
''',
    '''        capabilities = (
            resolve_production_feature_capabilities()
            if settings.is_managed
            else _development_capabilities()
        )
''',
    "resolve managed worker capabilities",
)
replace_once(
    worker,
    "    elif not settings.is_production:\n",
    "    elif settings.is_development:\n",
    "require configured search key outside development",
)
replace_once(
    worker,
    "    if capabilities.external_ai_enabled or not settings.is_production:\n",
    "    if capabilities.external_ai_enabled or settings.is_development:\n",
    "keep live provider registration fail-closed in staging",
)
replace_once(
    worker,
    '''    external_calls_enabled = (
        capabilities.external_ai_enabled
        if settings.is_production
        else _bool_env("AI_EXTERNAL_CALLS_ENABLED", default=False)
    )
''',
    '''    external_calls_enabled = (
        capabilities.external_ai_enabled
        if settings.is_managed
        else _bool_env("AI_EXTERNAL_CALLS_ENABLED", default=False)
    )
''',
    "apply managed external AI capability",
)
replace_once(
    worker,
    "            if settings.is_production\n",
    "            if settings.is_managed\n",
    "use secret-backed media tokens in staging",
)
replace_once(
    worker,
    '''    def publisher_service_factory() -> OutboxPublisherService:
        uow = integrated_uow_factory()
        return OutboxPublisherService(
''',
    '''    def publisher_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxPublisherService:
        return OutboxPublisherService(
''',
    "publisher uses active UoW",
)
replace_once(
    worker,
    '''    def processor_service_factory() -> OutboxProcessorService:
        uow = integrated_uow_factory()
        return OutboxProcessorService(
''',
    '''    def processor_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxProcessorService:
        return OutboxProcessorService(
''',
    "processor uses active UoW",
)
replace_once(
    worker,
    '''    def reconciliation_service_factory() -> OutboxReconciliationService:
        uow = integrated_uow_factory()
        return OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)
''',
    '''    def reconciliation_service_factory(
        uow: SqlAlchemyIntegratedUnitOfWork,
    ) -> OutboxReconciliationService:
        return OutboxReconciliationService(outbox_jobs=uow.outbox_jobs)
''',
    "reconciliation uses active UoW",
)

replace_once(
    worker_main,
    "            publisher = runtime.publisher_service_factory()\n",
    "            publisher = runtime.publisher_service_factory(uow)\n",
    "pass active UoW to publisher",
)
replace_once(
    worker_main,
    "        processor = runtime.processor_service_factory()\n",
    "        processor = runtime.processor_service_factory(uow)\n",
    "pass active UoW to processor",
)
replace_once(
    worker_main,
    "        reconciliation = runtime.reconciliation_service_factory()\n",
    "        reconciliation = runtime.reconciliation_service_factory(uow)\n",
    "pass active UoW to reconciliation",
)

replace_once(
    ops_encryption,
    "from closeros.infrastructure.static_key_provider import StaticKeyProvider\n",
    '''from closeros.infrastructure.staging_runtime import build_staging_key_provider_from_env
from closeros.infrastructure.static_key_provider import StaticKeyProvider
''',
    "import staging key provider",
)
replace_once(
    ops_encryption,
    '''def build_ops_content_encryption_service(
    uow_factory: Callable[[], IntegratedUnitOfWork],
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=development_key_provider(),
''',
    '''def environment_key_provider() -> StaticKeyProvider:
    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    if app_env == "staging":
        return build_staging_key_provider_from_env()
    if app_env == "production":
        raise RuntimeError(
            "operator scripts cannot use static encryption in production; use the remote KMS runtime"
        )
    if app_env != "development":
        raise RuntimeError("APP_ENV must be development, staging, or production")
    return development_key_provider()


def build_ops_content_encryption_service(
    uow_factory: Callable[[], IntegratedUnitOfWork],
) -> ContentEncryptionService:
    return ContentEncryptionService(
        data_key_cryptography=AesGcmContentCryptography(
            key_provider=environment_key_provider(),
''',
    "match operator encryption to environment",
)

print("explicit S2 staging runtime patch applied")
