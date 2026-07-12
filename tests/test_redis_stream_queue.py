"""Redis stream queue integration tests."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from closeros.infrastructure.redis_stream_queue import (
    RedisStreamJobConsumer,
    RedisStreamQueuePublisher,
)
from redis.asyncio import Redis

pytestmark = pytest.mark.redis_integration


def _redis_url() -> str | None:
    return os.environ.get("TEST_REDIS_URL") or os.environ.get("REDIS_URL")


@pytest.fixture
def redis_url() -> str:
    url = _redis_url()
    if url is None:
        pytest.skip("TEST_REDIS_URL or REDIS_URL is not configured")
    return url


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=False)
    yield client
    await client.aclose()


def test_redis_publisher_publishes_uuid_only(redis_url: str) -> None:
    async def exercise() -> None:
        stream = f"test.outbox.{uuid.uuid4().hex[:8]}"
        job_id = uuid.uuid4()
        redis = Redis.from_url(redis_url, decode_responses=False)
        publisher = RedisStreamQueuePublisher(redis=redis, stream_name=stream)
        try:
            await publisher.publish_job_id(job_id=job_id)
            entries = await redis.xrange(stream)
            assert entries is not None
            assert len(entries) == 1
            _, fields = entries[0]
            assert fields is not None
            raw_job_id = fields.get(b"job_id") or fields.get("job_id")
            if isinstance(raw_job_id, bytes):
                raw_job_id = raw_job_id.decode("utf-8")
            assert raw_job_id == str(job_id)
            assert b"tenant" not in str(fields).encode()
        finally:
            await publisher.close()
            await redis.delete(stream)
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_consumer_group_reads_and_acknowledges(redis_url: str) -> None:
    async def exercise() -> None:
        stream = f"test.outbox.{uuid.uuid4().hex[:8]}"
        group = f"test-group-{uuid.uuid4().hex[:8]}"
        consumer_name = "consumer-a"
        job_id = uuid.uuid4()
        redis = Redis.from_url(redis_url, decode_responses=False)
        publisher = RedisStreamQueuePublisher(redis=redis, stream_name=stream)
        consumer = RedisStreamJobConsumer(
            redis=redis,
            stream_name=stream,
            group_name=group,
            consumer_name=consumer_name,
            block_ms=100,
        )
        try:
            await publisher.publish_job_id(job_id=job_id)
            await consumer.ensure_group()
            messages = await consumer.read_job_ids()
            assert messages
            message_id, read_job_id = messages[0]
            assert read_job_id == job_id
            await consumer.acknowledge(message_id=message_id)
            pending = await redis.xpending(stream, group)
            assert pending["pending"] == 0
        finally:
            await publisher.close()
            await consumer.close()
            await redis.delete(stream)
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_consumer_group_creation_is_idempotent(redis_url: str) -> None:
    async def exercise() -> None:
        stream = f"test.outbox.{uuid.uuid4().hex[:8]}"
        group = f"test-group-{uuid.uuid4().hex[:8]}"
        redis = Redis.from_url(redis_url, decode_responses=False)
        consumer = RedisStreamJobConsumer(
            redis=redis,
            stream_name=stream,
            group_name=group,
            consumer_name="consumer-b",
            block_ms=100,
        )
        try:
            await consumer.ensure_group()
            await consumer.ensure_group()
        finally:
            await consumer.close()
            await redis.delete(stream)
            await redis.aclose()

    asyncio.run(exercise())
