"""Structured metadata-only logging helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class StructuredLogger:
    """JSON structured logger that never emits message bodies or secrets."""

    logger: logging.Logger
    service_name: str
    extra_fields: dict[str, str] = field(default_factory=dict)

    def _emit(self, level: int, event: str, fields: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": self.service_name,
            "event": event,
        }
        payload.update(self.extra_fields)
        if fields:
            payload.update(fields)
        self.logger.log(level, json.dumps(payload, separators=(",", ":"), sort_keys=True))

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields)


@dataclass
class SafeMetricsCollector:
    """In-process stdlib metrics collector without vendor SDK dependencies."""

    counters: dict[str, int] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)

    def increment(self, name: str, *, amount: int = 1) -> None:
        if amount < 1:
            raise ValueError("amount must be positive")
        self.counters[name] = self.counters.get(name, 0) + amount

    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
        }


def configure_structured_logging(*, service_name: str) -> StructuredLogger:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return StructuredLogger(logger=logging.getLogger(service_name), service_name=service_name)


__all__ = [
    "SafeMetricsCollector",
    "StructuredLogger",
    "configure_structured_logging",
]
