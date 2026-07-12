"""Redis Streams queue adapter for transactional outbox job publication."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError


class RedisStreamQueueError(Exception):
    """Base class for safe Redis stream queue failures."""


@dataclass(frozen=True, slots=True)
class RedisStreamQueuePublisher:
    """Publishes outbox job UUIDs to a Redis stream using XADD."""

    redis: Redis
    stream_name: str

    async def publish_job_id(self, *, job_id: UUID) -> None:
        try:
            await self.redis.xadd(self.stream_name, {"job_id": str(job_id)})
        except RedisError as error:
            raise RedisStreamQueueError("redis stream publish failed") from error

    async def close(self) -> None:
        try:
            await self.redis.aclose()
        except RedisError as error:
            raise RedisStreamQueueError("redis connection close failed") from error


@dataclass(frozen=True, slots=True)
class RedisStreamJobConsumer:
    """Consumes outbox job UUIDs from a Redis stream consumer group."""

    redis: Redis
    stream_name: str
    group_name: str
    consumer_name: str
    block_ms: int = 5_000
    autoclaim_idle_ms: int = 60_000
    read_count: int = 1

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise RedisStreamQueueError("redis consumer group creation failed") from error
        except RedisError as error:
            raise RedisStreamQueueError("redis consumer group creation failed") from error

    async def read_job_ids(self) -> tuple[tuple[str, UUID], ...]:
        try:
            autoclaimed = await self.redis.xautoclaim(
                self.stream_name,
                self.group_name,
                self.consumer_name,
                self.autoclaim_idle_ms,
                "0-0",
                count=self.read_count,
            )
            messages = _extract_messages(autoclaimed)
            if messages:
                return messages

            response = await self.redis.xreadgroup(
                self.group_name,
                self.consumer_name,
                {self.stream_name: ">"},
                count=self.read_count,
                block=self.block_ms,
            )
            return _extract_messages(response)
        except RedisError as error:
            raise RedisStreamQueueError("redis stream read failed") from error

    async def acknowledge(self, *, message_id: str) -> None:
        try:
            await self.redis.xack(self.stream_name, self.group_name, message_id)
        except RedisError as error:
            raise RedisStreamQueueError("redis stream acknowledgement failed") from error

    async def close(self) -> None:
        try:
            await self.redis.aclose()
        except RedisError as error:
            raise RedisStreamQueueError("redis connection close failed") from error


def _extract_messages(response: object) -> tuple[tuple[str, UUID], ...]:
    if not response:
        return ()

    entries: list[tuple[str, UUID]] = []

    if isinstance(response, tuple) and len(response) == 3:
        claimed_entries = response[1]
        if isinstance(claimed_entries, list):
            for message_id, fields in claimed_entries:
                job_id = _parse_job_id(fields)
                if job_id is not None:
                    normalized_message_id = (
                        message_id.decode("utf-8")
                        if isinstance(message_id, bytes)
                        else str(message_id)
                    )
                    entries.append((normalized_message_id, job_id))
        return tuple(entries)

    if not isinstance(response, list):
        return ()

    for stream_name, stream_messages in response:
        _ = stream_name
        if not isinstance(stream_messages, list):
            continue
        for message_id, fields in stream_messages:
            job_id = _parse_job_id(fields)
            if job_id is not None:
                normalized_message_id = (
                    message_id.decode("utf-8") if isinstance(message_id, bytes) else str(message_id)
                )
                entries.append((normalized_message_id, job_id))

    return tuple(entries)


def _parse_job_id(fields: object) -> UUID | None:
    if not isinstance(fields, dict):
        return None

    raw_job_id = fields.get("job_id") or fields.get(b"job_id")
    if raw_job_id is None:
        return None

    if isinstance(raw_job_id, bytes):
        raw_job_id = raw_job_id.decode("utf-8")

    if not isinstance(raw_job_id, str):
        return None

    try:
        return UUID(raw_job_id)
    except ValueError:
        return None
