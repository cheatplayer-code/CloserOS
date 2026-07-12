"""In-memory webhook rate limiter for development and tests."""

from __future__ import annotations


class InMemoryWebhookRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}

    async def check_webhook(
        self,
        *,
        scope_key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")

        import time

        now = time.time()
        window_start, count = self._windows.get(scope_key, (now, 0))
        if now - window_start >= window_seconds:
            self._windows[scope_key] = (now, 1)
            return True

        if count >= limit:
            return False

        self._windows[scope_key] = (window_start, count + 1)
        return True
