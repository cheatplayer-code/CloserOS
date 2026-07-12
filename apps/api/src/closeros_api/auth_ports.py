"""Authentication API ports and development adapters."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from closeros.application.authentication_workflows import (
    AuthenticationNotificationDelivery,
)
from closeros.domain.authentication import MfaMethod


class Clock(Protocol):
    def now(self) -> datetime: ...


class UuidFactory(Protocol):
    def __call__(self) -> UUID: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomUuidFactory:
    def __call__(self) -> UUID:
        return uuid4()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


class RateLimiter(Protocol):
    async def check(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision: ...


class NotificationDispatcher(Protocol):
    async def dispatch_email_verification(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None: ...

    async def dispatch_password_reset(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None: ...


class CaptureNotificationDispatcher:
    """Development/test dispatcher that records payloads without sending email."""

    def __init__(self) -> None:
        self.verification_deliveries: list[AuthenticationNotificationDelivery] = []
        self.reset_deliveries: list[AuthenticationNotificationDelivery] = []
        self.fail_next: Exception | None = None

    async def dispatch_email_verification(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise error
        self.verification_deliveries.append(delivery)

    async def dispatch_password_reset(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise error
        self.reset_deliveries.append(delivery)


class NoOpNotificationDispatcher:
    async def dispatch_email_verification(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        return None

    async def dispatch_password_reset(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        return None


@dataclass
class InMemoryRateLimiter:
    """Bounded in-memory limiter for development and tests."""

    _events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def check(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        composite_key = f"{scope}:{key}"
        now = datetime.now(UTC).timestamp()
        async with self._lock:
            bucket = self._events[composite_key]
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = int(window_seconds - (now - bucket[0])) + 1
                return RateLimitDecision(allowed=False, retry_after_seconds=max(retry_after, 1))
            bucket.append(now)
        return RateLimitDecision(allowed=True)


class ProductionRequiredRateLimiter:
    async def check(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        raise RuntimeError("production rate limiter is not configured")


class ProductionRequiredNotificationDispatcher:
    async def dispatch_email_verification(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        raise RuntimeError("production notification dispatcher is not configured")

    async def dispatch_password_reset(
        self,
        delivery: AuthenticationNotificationDelivery,
    ) -> None:
        raise RuntimeError("production notification dispatcher is not configured")


@dataclass
class ConfigurableMfaRequirementPolicy:
    """Non-production MFA policy controlled explicitly by configuration."""

    requires_mfa: bool = False

    async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
        return self.requires_mfa


class ProductionRequiredMfaRequirementPolicy:
    async def requires_mfa_for_user(self, *, user_id: UUID) -> bool:
        raise RuntimeError("production MFA requirement policy is not configured")


class CallableMfaVerifier:
    def __init__(
        self,
        handler: Callable[[UUID, MfaMethod, object], bool],
    ) -> None:
        self._handler = handler

    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool:
        return self._handler(user_id, method, response)


class AcceptingMfaVerifier:
    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool:
        return True
