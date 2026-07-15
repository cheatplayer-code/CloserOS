"""Typed worker settings loaded from the environment at call time."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

_DEVELOPMENT = "development"
_STAGING = "staging"
_PRODUCTION = "production"
_MANAGED_ENVIRONMENTS = frozenset({_STAGING, _PRODUCTION})


class WorkerConfigurationError(RuntimeError):
    """Raised when worker settings are missing or unsafe for the active environment."""


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    app_env: str
    database_url: str
    redis_url: str
    outbox_stream: str
    outbox_consumer_group: str
    worker_id: str
    polling_interval_seconds: float
    publish_batch_size: int
    processor_block_ms: int
    max_parallel_jobs: int
    shutdown_grace_seconds: float

    @property
    def is_production(self) -> bool:
        return self.app_env == _PRODUCTION

    @property
    def is_staging(self) -> bool:
        return self.app_env == _STAGING

    @property
    def is_development(self) -> bool:
        return self.app_env == _DEVELOPMENT

    @property
    def is_managed(self) -> bool:
        return self.app_env in _MANAGED_ENVIRONMENTS

    @classmethod
    def from_env(cls) -> WorkerSettings:
        app_env = os.environ.get("APP_ENV", _DEVELOPMENT).strip().lower()
        if app_env not in {_DEVELOPMENT, _STAGING, _PRODUCTION}:
            raise WorkerConfigurationError("APP_ENV must be development, staging, or production")

        database_url = os.environ.get("DATABASE_URL", "").strip()
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if app_env in _MANAGED_ENVIRONMENTS:
            if not database_url:
                raise WorkerConfigurationError("DATABASE_URL is not set")
            if not redis_url:
                raise WorkerConfigurationError("REDIS_URL is not set")
        else:
            database_url = database_url or (
                "postgresql://closeros_local:closeros_local_only_change_me"
                "@127.0.0.1:5432/closeros_local"
            )
            redis_url = redis_url or (
                "redis://:closeros_local_redis_only_change_me@127.0.0.1:6379/0"
            )

        outbox_stream = os.environ.get("OUTBOX_STREAM", "closeros.outbox.jobs").strip()
        outbox_consumer_group = os.environ.get(
            "OUTBOX_CONSUMER_GROUP",
            "closeros.outbox.processors",
        ).strip()
        worker_id = os.environ.get("WORKER_ID", "").strip()
        if not worker_id:
            worker_id = f"worker-{uuid.uuid4().hex[:12]}"

        polling_interval_seconds = _positive_float_from_env(
            variable_name="WORKER_POLLING_INTERVAL_SECONDS",
            default=1.0,
        )
        publish_batch_size = _positive_int_from_env(
            variable_name="WORKER_PUBLISH_BATCH_SIZE",
            default=25,
        )
        processor_block_ms = _positive_int_from_env(
            variable_name="WORKER_PROCESSOR_BLOCK_MS",
            default=5_000,
        )
        max_parallel_jobs = _positive_int_from_env(
            variable_name="WORKER_MAX_PARALLEL_JOBS",
            default=4,
        )
        shutdown_grace_seconds = _positive_float_from_env(
            variable_name="WORKER_SHUTDOWN_GRACE_SECONDS",
            default=30.0,
        )

        return cls(
            app_env=app_env,
            database_url=database_url,
            redis_url=redis_url,
            outbox_stream=outbox_stream,
            outbox_consumer_group=outbox_consumer_group,
            worker_id=worker_id,
            polling_interval_seconds=polling_interval_seconds,
            publish_batch_size=publish_batch_size,
            processor_block_ms=processor_block_ms,
            max_parallel_jobs=max_parallel_jobs,
            shutdown_grace_seconds=shutdown_grace_seconds,
        )


def _positive_int_from_env(*, variable_name: str, default: int) -> int:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as error:
        raise WorkerConfigurationError(f"{variable_name} must be an integer") from error
    if parsed <= 0:
        raise WorkerConfigurationError(f"{variable_name} must be positive")
    return parsed


def _positive_float_from_env(*, variable_name: str, default: float) -> float:
    raw_value = os.environ.get(variable_name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except ValueError as error:
        raise WorkerConfigurationError(f"{variable_name} must be a number") from error
    if parsed <= 0:
        raise WorkerConfigurationError(f"{variable_name} must be positive")
    return parsed
