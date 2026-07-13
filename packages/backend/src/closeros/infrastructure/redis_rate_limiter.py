"""Redis-backed webhook rate limiter with atomic fixed-window counting.

Fail-closed scopes (return ``False`` on deny or infrastructure failure):
- ``webhook:{provider_kind}`` — global per-provider webhook acceptance;
- any scope where Redis is unavailable, misconfigured, or returns an error.

Keys are hashed (SHA-256 prefix) so scope identifiers never store raw PII.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if current > tonumber(ARGV[2]) then
  return 0
end
return 1
"""


def _hash_scope_key(scope_key: str) -> str:
    if not isinstance(scope_key, str) or not scope_key.strip():
        raise ValueError("scope_key must be a non-empty string")
    digest = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()[:32]
    return f"rl:{digest}"


@dataclass(frozen=True, slots=True)
class RedisWebhookRateLimiter:
    """Production webhook rate limiter using Redis Lua INCR+EXPIRE."""

    redis: Redis
    key_prefix: str = "closeros"

    async def check_webhook(
        self,
        *,
        scope_key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")

        hashed = _hash_scope_key(scope_key)
        redis_key = f"{self.key_prefix}:{hashed}"
        try:
            allowed = await self.redis.eval(
                _RATE_LIMIT_LUA,
                1,
                redis_key,
                str(window_seconds),
                str(limit),
            )
        except RedisError:
            return False

        return bool(allowed)


__all__ = ["RedisWebhookRateLimiter", "_hash_scope_key"]
