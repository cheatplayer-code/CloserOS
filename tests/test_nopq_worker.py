"""Worker runtime tests for NOPQ additions."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from closeros.application.knowledge_index_handler import KnowledgeIndexHandler
from closeros.domain.outbox import OutboxJobKind
from closeros.infrastructure.database import create_authentication_engine
from closeros_worker.runtime import (
    LM_SUPPORTED_JOB_KINDS,
    WorkerRuntimeOverrides,
    build_worker_runtime,
)
from closeros_worker.settings import WorkerSettings
from redis.asyncio import Redis

from tests.encryption_support import SERVICE_ID


class _NoopRedis:
    async def aclose(self) -> None:
        return None


def _settings(database_url: str) -> WorkerSettings:
    return WorkerSettings(
        app_env="development",
        database_url=database_url,
        redis_url="redis://127.0.0.1:6379/0",
        outbox_stream="closeros.outbox.jobs",
        outbox_consumer_group="closeros.outbox.processors",
        worker_id="nopq-worker-test",
        polling_interval_seconds=1.0,
        publish_batch_size=25,
        processor_block_ms=5_000,
    )


def test_lm_supported_job_kinds_include_knowledge_index() -> None:
    assert OutboxJobKind.KNOWLEDGE_INDEX in LM_SUPPORTED_JOB_KINDS


def test_nopq_supported_job_kinds_include_message_analyze() -> None:
    assert OutboxJobKind.MESSAGE_ANALYZE in LM_SUPPORTED_JOB_KINDS


def test_worker_runtime_registers_knowledge_index_handler(
    auth_test_database_url: str,
    auth_session_factory: Any,
) -> None:
    engine = create_authentication_engine(auth_test_database_url)

    async def exercise() -> None:
        runtime = build_worker_runtime(
            _settings(auth_test_database_url),
            overrides=WorkerRuntimeOverrides(
                engine=engine,
                session_factory=auth_session_factory,
                redis=cast(Redis, _NoopRedis()),
                ingestion_service_id=SERVICE_ID,
            ),
        )
        try:
            assert OutboxJobKind.KNOWLEDGE_INDEX in runtime.handlers
            assert isinstance(
                runtime.handlers[OutboxJobKind.KNOWLEDGE_INDEX], KnowledgeIndexHandler
            )
        finally:
            await runtime.dispose()

    asyncio.run(exercise())
