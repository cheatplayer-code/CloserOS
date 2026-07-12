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
    _extract_xautoclaim_messages,
    _extract_xreadgroup_messages,
    _parse_job_id,
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


def test_xautoclaim_empty_list_response_returns_empty_tuple() -> None:
    assert _extract_xautoclaim_messages([b"0-0", [], []]) == ()


def test_xautoclaim_list_response_with_one_valid_job() -> None:
    job_id = uuid.uuid4()
    response = [
        b"0-0",
        [
            [b"1712345678901-0", {b"job_id": str(job_id).encode("ascii")}],
        ],
        [],
    ]
    assert _extract_xautoclaim_messages(response) == (("1712345678901-0", job_id),)


def test_xautoclaim_tuple_response_with_one_valid_job() -> None:
    job_id = uuid.uuid4()
    response: tuple[object, list[object], list[object]] = (
        b"0-0",
        [
            (b"1712345678902-0", {b"job_id": str(job_id).encode("ascii")}),
        ],
        [],
    )
    assert _extract_xautoclaim_messages(response) == (("1712345678902-0", job_id),)


def test_xreadgroup_response_with_one_stream_and_one_message() -> None:
    job_id = uuid.uuid4()
    response = [
        [
            b"stream-name",
            [
                [b"1712345678903-0", {b"job_id": str(job_id).encode("ascii")}],
            ],
        ],
    ]
    assert _extract_xreadgroup_messages(response) == (("1712345678903-0", job_id),)


def test_xreadgroup_response_with_multiple_messages() -> None:
    job_id_one = uuid.uuid4()
    job_id_two = uuid.uuid4()
    response = [
        [
            b"stream-name",
            [
                [b"1712345678904-0", {b"job_id": str(job_id_one).encode("ascii")}],
                [b"1712345678905-0", {b"job_id": str(job_id_two).encode("ascii")}],
            ],
        ],
    ]
    assert _extract_xreadgroup_messages(response) == (
        ("1712345678904-0", job_id_one),
        ("1712345678905-0", job_id_two),
    )


def test_parsers_support_decoded_string_responses() -> None:
    job_id = uuid.uuid4()
    autoclaim = [
        "0-0",
        [
            ["1712345678906-0", {"job_id": str(job_id)}],
        ],
        [],
    ]
    xreadgroup = [
        [
            "stream-name",
            [
                ["1712345678907-0", {"job_id": str(job_id)}],
            ],
        ],
    ]
    assert _extract_xautoclaim_messages(autoclaim) == (("1712345678906-0", job_id),)
    assert _extract_xreadgroup_messages(xreadgroup) == (("1712345678907-0", job_id),)


def test_malformed_response_elements_do_not_raise() -> None:
    assert _extract_xautoclaim_messages([b"0-0"]) == ()
    assert _extract_xautoclaim_messages("not-a-response") == ()
    assert _extract_xautoclaim_messages([b"0-0", "not-a-list", []]) == ()
    assert _extract_xautoclaim_messages([b"0-0", [[b"1-0"]], []]) == ()
    assert _extract_xreadgroup_messages(None) == ()
    assert _extract_xreadgroup_messages([["stream-only"]]) == ()
    assert _extract_xreadgroup_messages([[b"stream", "not-a-list"]]) == ()
    assert _extract_xreadgroup_messages([[b"stream", [[b"1-0"]]]]) == ()


def test_invalid_uuid_values_are_skipped() -> None:
    autoclaim = [
        b"0-0",
        [
            [b"1712345678908-0", {b"job_id": b"not-a-uuid"}],
        ],
        [],
    ]
    xreadgroup = [
        [
            b"stream-name",
            [
                [b"1712345678909-0", {b"job_id": b"still-not-a-uuid"}],
            ],
        ],
    ]
    assert _extract_xautoclaim_messages(autoclaim) == ()
    assert _extract_xreadgroup_messages(xreadgroup) == ()
    assert _parse_job_id({b"job_id": b"not-a-uuid"}) is None
