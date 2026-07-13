"""Redis-backed distributed rate limiter for auth and webhook scopes.

Uses an atomic Lua fixed-window counter (INCR + EXPIRE on first hit). Redis keys are
derived with HMAC-SHA256 using ``REDIS_RATE_LIMIT_HMAC_SECRET`` so raw identifiers
never appear in key names::

    closeros:rl:<hmac_hex>

Fail-closed scopes (deny when Redis is unavailable, misconfigured, or errors):

- all authentication and mutation scopes listed in ``RateLimitScope`` except
  ``RateLimitScope.DIAGNOSTICS``;
- ``webhook:*`` scopes via ``check_webhook``.

Read-only fail-open (documented exception):

- ``RateLimitScope.DIAGNOSTICS`` — observability endpoints may degrade open when
  Redis is unavailable so operators can still inspect process health. All other
  scopes remain fail-closed in production.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local limit = tonumber(ARGV[2])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  ttl = tonumber(ARGV[1])
end
if current > limit then
  return {0, 0, ttl}
end
return {1, limit - current, ttl}
"""

_KEY_PREFIX = "closeros:rl:"


class RateLimitScope:
    REGISTRATION = "register"
    LOGIN = "login"
    MFA = "mfa"
    VERIFICATION = "verification"
    PASSWORD_RESET = "password_reset"
    WEBHOOKS = "webhooks"
    OUTBOUND = "outbound"
    AI = "ai"
    KNOWLEDGE = "knowledge"
    CRM = "crm"
    WHATSAPP = "whatsapp"
    RETENTION = "retention"
    DIAGNOSTICS = "diagnostics"


_SENSITIVE_SCOPES = frozenset(
    {
        RateLimitScope.REGISTRATION,
        RateLimitScope.LOGIN,
        RateLimitScope.MFA,
        RateLimitScope.VERIFICATION,
        RateLimitScope.PASSWORD_RESET,
        RateLimitScope.WEBHOOKS,
        RateLimitScope.OUTBOUND,
        RateLimitScope.AI,
        RateLimitScope.KNOWLEDGE,
        RateLimitScope.CRM,
        RateLimitScope.WHATSAPP,
        RateLimitScope.RETENTION,
    }
)

_READ_ONLY_FAIL_OPEN_SCOPES = frozenset({RateLimitScope.DIAGNOSTICS})


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


def _validate_positive_int(value: int, *, name: str) -> None:
    if value < 1:
        raise ValueError(f"{name} must be positive")


def derive_rate_limit_key(*, scope: str, identifier: str, hmac_secret: bytes) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("scope must be a non-empty string")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("identifier must be a non-empty string")
    if not hmac_secret:
        raise ValueError("hmac_secret must not be empty")

    message = f"{scope}:{identifier}".encode()
    digest = hmac.new(hmac_secret, message, hashlib.sha256).hexdigest()
    return f"{_KEY_PREFIX}{digest}"


@dataclass(frozen=True, slots=True)
class RedisDistributedRateLimiter:
    """Production rate limiter shared by auth and webhook ports."""

    redis: Redis
    hmac_secret: bytes

    async def check(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        _validate_positive_int(limit, name="limit")
        _validate_positive_int(window_seconds, name="window_seconds")
        redis_key = derive_rate_limit_key(
            scope=scope,
            identifier=key,
            hmac_secret=self.hmac_secret,
        )
        try:
            return await self._evaluate(
                redis_key=redis_key,
                limit=limit,
                window_seconds=window_seconds,
            )
        except RedisError:
            return self._failure_result(
                scope=scope,
                limit=limit,
                window_seconds=window_seconds,
            )

    async def check_webhook(
        self,
        *,
        scope_key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        _validate_positive_int(limit, name="limit")
        _validate_positive_int(window_seconds, name="window_seconds")
        redis_key = derive_rate_limit_key(
            scope=RateLimitScope.WEBHOOKS,
            identifier=scope_key,
            hmac_secret=self.hmac_secret,
        )
        try:
            result = await self._evaluate(
                redis_key=redis_key,
                limit=limit,
                window_seconds=window_seconds,
            )
        except RedisError:
            return False
        return result.allowed

    async def _evaluate(
        self,
        *,
        redis_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        raw = await self.redis.eval(
            _RATE_LIMIT_LUA,
            1,
            redis_key,
            str(window_seconds),
            str(limit),
        )
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise RedisError("unexpected rate limit script response")

        allowed = bool(int(raw[0]))
        remaining = max(int(raw[1]), 0)
        retry_after = max(int(raw[2]), 1)
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            retry_after_seconds=None if allowed else retry_after,
        )

    def _failure_result(
        self,
        *,
        scope: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        if scope in _READ_ONLY_FAIL_OPEN_SCOPES:
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                retry_after_seconds=None,
            )
        if scope in _SENSITIVE_SCOPES or scope.startswith("webhook:"):
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=window_seconds,
            )
        return RateLimitResult(
            allowed=False,
            remaining=0,
            retry_after_seconds=window_seconds,
        )


__all__ = [
    "RateLimitResult",
    "RateLimitScope",
    "RedisDistributedRateLimiter",
    "derive_rate_limit_key",
]
