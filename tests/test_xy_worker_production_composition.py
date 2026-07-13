"""Production worker composition tests without live infrastructure."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from closeros.application.knowledge_index_handler import KnowledgeIndexHandler
from closeros.application.knowledge_search_key import DevKnowledgeSearchKeyProvider
from closeros.domain.outbox import OutboxJobKind
from closeros.infrastructure.env_knowledge_search_key_provider import (
    EnvKnowledgeSearchKeyProvider,
)
from closeros.infrastructure.production_runtime import (
    ProductionConfigurationError,
    build_production_shared_runtime,
)
from closeros_worker import __main__ as worker_main
from closeros_worker.runtime import (
    _merge_production_worker_overrides,
    build_worker_runtime,
)
from closeros_worker.settings import WorkerSettings

from tests.database_url_support import placeholder_database_url

_INGESTION_SERVICE_ID = UUID("00000000-0000-0000-0000-00000000e001")


def _placeholder_database_url() -> str:
    return placeholder_database_url()


def _minimal_production_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": _placeholder_database_url(),
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_RATE_LIMIT_HMAC_SECRET": "rate-limit-secret-value-32-bytes",
        "KMS_BASE_URL": "https://kms.example.test",
        "KMS_API_TOKEN_REF": "env:KMS_API_TOKEN",
        "KMS_API_TOKEN": "synthetic-kms-token-value",
        "KMS_ACTIVE_KEY_VERSION": "v1",
        "KMS_KEY_VERSIONS": "v1",
        "KNOWLEDGE_SEARCH_KEY_REF": "env:KNOWLEDGE_SEARCH_KEY",
        "KNOWLEDGE_SEARCH_KEY": "a" * 32,
        "INGESTION_SERVICE_ID": str(_INGESTION_SERVICE_ID),
        "WORKER_ID": "xy-production-worker-test",
        "AUTH_ALLOWED_ORIGINS": "https://app.example",
        "AUTH_CSRF_SECRET": "a" * 32,
        "AUTH_RATE_LIMIT_SECRET": "b" * 32,
    }


def _production_worker_settings() -> WorkerSettings:
    return WorkerSettings(
        app_env="production",
        database_url=_placeholder_database_url(),
        redis_url="redis://127.0.0.1:6379/0",
        outbox_stream="closeros.outbox.jobs",
        outbox_consumer_group="closeros.outbox.processors",
        worker_id="xy-production-worker-test",
        polling_interval_seconds=1.0,
        publish_batch_size=25,
        processor_block_ms=5_000,
        max_parallel_jobs=4,
        shutdown_grace_seconds=30.0,
    )


class _NoopRedis:
    async def aclose(self) -> None:
        return None

    async def ping(self) -> bool:
        return True


@pytest.fixture
def minimal_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "WHATSAPP_ENABLED",
        "CRM_ENABLED",
        "NOTIFICATIONS_ENABLED",
        "CLAMAV_ENABLED",
        "MEDIA_SCANNING_ENABLED",
        "AI_EXTERNAL_CALLS_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    for name, value in _minimal_production_env().items():
        monkeypatch.setenv(name, value)


def test_build_production_shared_runtime_accepts_minimal_disabled_features(
    minimal_production_env: None,
) -> None:
    with patch(
        "closeros.infrastructure.production_runtime.Redis.from_url",
        return_value=cast(Any, _NoopRedis()),
    ):
        shared = build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )
    assert shared.capabilities.whatsapp_enabled is False
    assert shared.capabilities.crm_enabled is False
    assert isinstance(shared.knowledge_search_key_provider, EnvKnowledgeSearchKeyProvider)


def test_build_production_shared_runtime_requires_kms(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KMS_BASE_URL", raising=False)
    with pytest.raises(ProductionConfigurationError, match="KMS_BASE_URL"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_build_production_shared_runtime_requires_redis(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ProductionConfigurationError, match="REDIS_URL"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_enabled_whatsapp_requires_credentials(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATSAPP_ENABLED", "true")
    monkeypatch.delenv("WHATSAPP_APP_SECRET_REF", raising=False)
    with pytest.raises(ProductionConfigurationError, match="WHATSAPP_APP_SECRET_REF"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_enabled_crm_requires_credentials(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRM_ENABLED", "true")
    monkeypatch.delenv("BITRIX24_PORTAL_DOMAIN", raising=False)
    with pytest.raises(ProductionConfigurationError, match="BITRIX24_PORTAL_DOMAIN"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_enabled_scanner_requires_config(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_SCANNING_ENABLED", "true")
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    with pytest.raises(ProductionConfigurationError, match="CLAMAV_HOST"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_enabled_external_ai_requires_deepseek_config(
    minimal_production_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_EXTERNAL_CALLS_ENABLED", "true")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProductionConfigurationError, match="DEEPSEEK_API_KEY"):
        build_production_shared_runtime(
            database_url=_placeholder_database_url(),
            ingestion_service_id=_INGESTION_SERVICE_ID,
        )


def test_merge_production_worker_overrides_builds_shared_runtime_when_unset(
    minimal_production_env: None,
) -> None:
    settings = _production_worker_settings()
    with patch(
        "closeros_worker.runtime.build_production_shared_runtime",
        return_value=MagicMock(
            engine=MagicMock(),
            session_factory=MagicMock(),
            integrated_uow_factory=MagicMock(),
            key_provider=MagicMock(),
            redis=cast(Any, _NoopRedis()),
            knowledge_search_key_provider=MagicMock(),
            capabilities=MagicMock(
                whatsapp_enabled=False,
                crm_enabled=False,
                notifications_enabled=False,
                media_scanning_enabled=False,
                external_ai_enabled=False,
            ),
            secret_resolver=MagicMock(),
            content_encryption=MagicMock(),
        ),
    ) as shared_builder:
        merged = _merge_production_worker_overrides(settings, overrides=None)
    shared_builder.assert_called_once()
    assert merged.engine is not None
    assert merged.redis is not None
    assert merged.knowledge_search_key_provider is not None


def test_disabled_optional_integrations_do_not_require_feature_flags(
    minimal_production_env: None,
) -> None:
    settings = _production_worker_settings()
    with patch(
        "closeros_worker.runtime.build_production_shared_runtime",
    ) as shared_builder:
        shared_builder.return_value = MagicMock(
            engine=MagicMock(),
            session_factory=MagicMock(),
            integrated_uow_factory=MagicMock(),
            key_provider=MagicMock(),
            redis=cast(Any, _NoopRedis()),
            knowledge_search_key_provider=EnvKnowledgeSearchKeyProvider(
                secret_reference="env:KNOWLEDGE_SEARCH_KEY",
                search_key_version="v1",
            ),
            capabilities=MagicMock(
                whatsapp_enabled=False,
                crm_enabled=False,
                notifications_enabled=False,
                media_scanning_enabled=False,
                external_ai_enabled=False,
            ),
            secret_resolver=MagicMock(),
            content_encryption=MagicMock(),
        )
        merged = _merge_production_worker_overrides(settings, overrides=None)
    assert merged.capabilities is not None
    assert merged.capabilities.whatsapp_enabled is False
    assert merged.capabilities.crm_enabled is False


def test_build_worker_runtime_uses_env_knowledge_key_provider_in_production(
    minimal_production_env: None,
) -> None:
    settings = _production_worker_settings()
    with patch(
        "closeros_worker.runtime.build_production_shared_runtime",
    ) as shared_builder:
        shared_builder.return_value = MagicMock(
            engine=MagicMock(dispose=MagicMock(return_value=None)),
            session_factory=MagicMock(),
            integrated_uow_factory=MagicMock(),
            key_provider=MagicMock(),
            adapter_registry=MagicMock(),
            redis=cast(Any, _NoopRedis()),
            knowledge_search_key_provider=EnvKnowledgeSearchKeyProvider(
                secret_reference="env:KNOWLEDGE_SEARCH_KEY",
                search_key_version="v1",
            ),
            capabilities=MagicMock(
                whatsapp_enabled=False,
                crm_enabled=False,
                notifications_enabled=False,
                media_scanning_enabled=False,
                external_ai_enabled=False,
            ),
            secret_resolver=MagicMock(),
            content_encryption=MagicMock(),
        )
        runtime = build_worker_runtime(settings)
    handler = runtime.handlers[OutboxJobKind.KNOWLEDGE_INDEX]
    assert isinstance(handler, KnowledgeIndexHandler)
    assert isinstance(handler.key_provider, EnvKnowledgeSearchKeyProvider)
    assert not isinstance(handler.key_provider, DevKnowledgeSearchKeyProvider)


def test_placeholder_database_url_is_composed_at_runtime() -> None:
    from tests.database_url_support import (
        test_placeholder_database_url_is_composed_at_runtime as _assert_runtime_url,
    )

    _assert_runtime_url()


async def _exercise_worker_processor_entrypoint(minimal_production_env: None) -> None:
    mock_runtime = MagicMock()
    mock_runtime.dispose = AsyncMock(return_value=None)
    loop = MagicMock()
    loop.add_signal_handler = MagicMock()

    with (
        patch(
            "closeros_worker.__main__.build_worker_runtime",
            return_value=mock_runtime,
        ) as build_runtime,
        patch(
            "closeros_worker.__main__._run_processor",
            new_callable=AsyncMock,
        ),
        patch(
            "closeros_worker.__main__.asyncio.get_running_loop",
            return_value=loop,
        ),
    ):
        exit_code = await worker_main._async_main("processor")

    build_runtime.assert_called_once()
    settings_arg = build_runtime.call_args.args[0]
    assert isinstance(settings_arg, WorkerSettings)
    assert build_runtime.call_args.kwargs == {}
    mock_runtime.dispose.assert_awaited_once()
    assert exit_code == 0


def test_worker_processor_entrypoint_builds_environment_runtime(
    minimal_production_env: None,
) -> None:
    asyncio.run(_exercise_worker_processor_entrypoint(minimal_production_env))


def test_production_app_factory_uses_environment_runtime_without_overrides(
    minimal_production_env: None,
) -> None:
    from closeros_api.composition import build_api_runtime
    from closeros_api.settings import ApiSettings

    shared = MagicMock(
        engine=MagicMock(dispose=MagicMock(return_value=None)),
        session_factory=MagicMock(),
        integrated_uow_factory=MagicMock(),
        key_provider=MagicMock(),
        redis=cast(Any, _NoopRedis()),
        knowledge_search_key_provider=MagicMock(),
        capabilities=MagicMock(
            whatsapp_enabled=False,
            crm_enabled=False,
            notifications_enabled=False,
            media_scanning_enabled=False,
            external_ai_enabled=False,
        ),
        secret_resolver=MagicMock(),
        content_encryption=MagicMock(),
        rate_limiter=MagicMock(),
    )
    settings = ApiSettings.from_env()
    with patch(
        "closeros_api.composition.build_production_shared_runtime",
        return_value=shared,
    ) as shared_builder:
        runtime = build_api_runtime(settings, overrides=None)
    shared_builder.assert_called_once()
    assert runtime.integrated_uow_factory is not None


def test_worker_processor_entrypoint_uses_build_worker_runtime_without_overrides() -> None:
    source = inspect.getsource(worker_main._async_main)
    assert "build_worker_runtime(settings)" in source
    assert "build_worker_runtime(settings," not in source


def test_worker_main_module_invokes_processor_mode() -> None:
    main_path = Path(worker_main.__file__)
    text = main_path.read_text(encoding="utf-8")
    assert "python -m closeros_worker" not in text
    assert '"processor"' in text
    assert "build_worker_runtime(settings)" in text
