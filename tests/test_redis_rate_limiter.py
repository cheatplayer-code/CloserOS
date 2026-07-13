"""Tests for Redis distributed rate limiter."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from closeros.infrastructure.redis_distributed_rate_limiter import (
    RateLimitScope,
    RedisDistributedRateLimiter,
    derive_rate_limit_key,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError

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
def hmac_secret() -> bytes:
    return b"test-rate-limit-hmac-secret-32-bytes!!"


def test_derive_key_never_contains_raw_identifier(hmac_secret: bytes) -> None:
    identifier = "user@example.com:203.0.113.10"
    derived = derive_rate_limit_key(
        scope=RateLimitScope.LOGIN,
        identifier=identifier,
        hmac_secret=hmac_secret,
    )
    assert derived.startswith("closeros:rl:")
    assert "user@example.com" not in derived
    assert "203.0.113.10" not in derived


def test_derive_key_separates_scope_buckets(hmac_secret: bytes) -> None:
    identifier = "same-key-material"
    login_key = derive_rate_limit_key(
        scope=RateLimitScope.LOGIN,
        identifier=identifier,
        hmac_secret=hmac_secret,
    )
    register_key = derive_rate_limit_key(
        scope=RateLimitScope.REGISTRATION,
        identifier=identifier,
        hmac_secret=hmac_secret,
    )
    assert login_key != register_key


def test_redis_rate_limiter_allows_within_limit(redis_url: str, hmac_secret: bytes) -> None:
    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=False)
        limiter = RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)
        scope_key = f"synthetic:{uuid.uuid4()}"
        try:
            first = await limiter.check(
                scope=RateLimitScope.LOGIN,
                key=scope_key,
                limit=2,
                window_seconds=60,
            )
            second = await limiter.check(
                scope=RateLimitScope.LOGIN,
                key=scope_key,
                limit=2,
                window_seconds=60,
            )
            third = await limiter.check(
                scope=RateLimitScope.LOGIN,
                key=scope_key,
                limit=2,
                window_seconds=60,
            )
            assert first.allowed is True
            assert first.remaining == 1
            assert second.allowed is True
            assert second.remaining == 0
            assert third.allowed is False
            assert third.remaining == 0
            assert third.retry_after_seconds is not None
            assert third.retry_after_seconds >= 1
        finally:
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_rate_limiter_webhook_boundary(redis_url: str, hmac_secret: bytes) -> None:
    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=False)
        limiter = RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)
        scope = f"webhook:synthetic:{uuid.uuid4()}"
        try:
            assert await limiter.check_webhook(scope_key=scope, limit=1, window_seconds=60)
            assert not await limiter.check_webhook(scope_key=scope, limit=1, window_seconds=60)
        finally:
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_rate_limiter_ttl_resets_window(redis_url: str, hmac_secret: bytes) -> None:
    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=False)
        limiter = RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)
        scope_key = f"ttl:{uuid.uuid4()}"
        try:
            assert (
                await limiter.check(
                    scope=RateLimitScope.VERIFICATION,
                    key=scope_key,
                    limit=1,
                    window_seconds=1,
                )
            ).allowed
            assert not (
                await limiter.check(
                    scope=RateLimitScope.VERIFICATION,
                    key=scope_key,
                    limit=1,
                    window_seconds=1,
                )
            ).allowed
            await asyncio.sleep(1.1)
            assert (
                await limiter.check(
                    scope=RateLimitScope.VERIFICATION,
                    key=scope_key,
                    limit=1,
                    window_seconds=1,
                )
            ).allowed
        finally:
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_rate_limiter_concurrent_requests_respect_limit(
    redis_url: str,
    hmac_secret: bytes,
) -> None:
    async def exercise() -> None:
        redis = Redis.from_url(redis_url, decode_responses=False)
        limiter = RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)
        scope_key = f"concurrent:{uuid.uuid4()}"
        try:

            async def hit() -> bool:
                result = await limiter.check(
                    scope=RateLimitScope.MFA,
                    key=scope_key,
                    limit=3,
                    window_seconds=60,
                )
                return result.allowed

            results = await asyncio.gather(*[hit() for _ in range(10)])
            assert sum(results) == 3
        finally:
            await redis.aclose()

    asyncio.run(exercise())


def test_redis_rate_limiter_fails_closed_on_invalid_args(hmac_secret: bytes) -> None:
    limiter = RedisDistributedRateLimiter(
        redis=Redis.from_url("redis://127.0.0.1:6379/0"),
        hmac_secret=hmac_secret,
    )
    with pytest.raises(ValueError):
        asyncio.run(
            limiter.check(
                scope=RateLimitScope.LOGIN,
                key="k",
                limit=0,
                window_seconds=60,
            )
        )


def test_redis_rate_limiter_fails_closed_on_redis_error(hmac_secret: bytes) -> None:
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=RedisError("down"))
    limiter = RedisDistributedRateLimiter(redis=redis, hmac_secret=hmac_secret)

    async def exercise() -> None:
        login = await limiter.check(
            scope=RateLimitScope.LOGIN,
            key="k",
            limit=5,
            window_seconds=60,
        )
        webhook = await limiter.check_webhook(
            scope_key="webhook:test",
            limit=5,
            window_seconds=60,
        )
        diagnostics = await limiter.check(
            scope=RateLimitScope.DIAGNOSTICS,
            key="k",
            limit=5,
            window_seconds=60,
        )
        assert login.allowed is False
        assert webhook is False
        assert diagnostics.allowed is True

    asyncio.run(exercise())
