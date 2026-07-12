"""Framework-independent deterministic metrics domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_FORMULA_VERSION_PATTERN = re.compile(r"^lm-metrics-v[0-9]+$")
_METRIC_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_WINDOW_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

_MAX_BASIS_POINTS = 10_000
_MAX_METRIC_VALUE = 1_000_000_000


class MetricScope(StrEnum):
    TENANT = "tenant"
    MANAGER = "manager"


class MetricSnapshotStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricKey(StrEnum):
    INBOUND_MESSAGE_COUNT = "inbound_message_count"
    OUTBOUND_MANAGER_MESSAGE_COUNT = "outbound_manager_message_count"
    ACTIVE_THREAD_COUNT = "active_thread_count"
    INBOUND_THREAD_COUNT = "inbound_thread_count"
    RESPONDED_THREAD_COUNT = "responded_thread_count"
    UNRESPONDED_THREAD_COUNT = "unresponded_thread_count"
    RESPONSE_RATE_BASIS_POINTS = "response_rate_basis_points"
    FIRST_RESPONSE_SAMPLE_COUNT = "first_response_sample_count"
    MEDIAN_FIRST_RESPONSE_SECONDS = "median_first_response_seconds"
    P90_FIRST_RESPONSE_SECONDS = "p90_first_response_seconds"
    FAILED_DELIVERY_COUNT = "failed_delivery_count"
    APPOINTMENT_BOOKED_CASE_COUNT = "appointment_booked_case_count"
    WON_CASE_COUNT = "won_case_count"
    LOST_CASE_COUNT = "lost_case_count"
    CONVERSION_RATE_BASIS_POINTS = "conversion_rate_basis_points"


METRIC_FORMULA_VERSION = "lm-metrics-v1"

_BASIS_POINT_METRICS = frozenset(
    {
        MetricKey.RESPONSE_RATE_BASIS_POINTS,
        MetricKey.CONVERSION_RATE_BASIS_POINTS,
    }
)


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if value > _MAX_METRIC_VALUE:
        raise ValueError(f"{field_name} exceeds maximum metric value")
    return value


def _validate_formula_version(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("formula_version must be a string")
    normalized = value.strip()
    if not _FORMULA_VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("formula_version has invalid format")
    return normalized


@dataclass(frozen=True, slots=True)
class MetricWindow:
    start: datetime
    end: datetime
    window_code: str

    def __post_init__(self) -> None:
        start = _validate_timezone_aware_datetime(self.start, "start")
        end = _validate_timezone_aware_datetime(self.end, "end")
        if end <= start:
            raise ValueError("window end must be after start")
        if not isinstance(self.window_code, str):
            raise TypeError("window_code must be a string")
        normalized_code = self.window_code.strip()
        if not _WINDOW_CODE_PATTERN.fullmatch(normalized_code):
            raise ValueError("window_code has invalid format")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "window_code", normalized_code)


@dataclass(frozen=True, slots=True)
class MetricValue:
    key: MetricKey
    value: int
    numerator: int | None = None
    denominator: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, MetricKey):
            raise TypeError("key must be a MetricKey")
        value = _validate_non_negative_int(self.value, "value")
        object.__setattr__(self, "value", value)

        if self.key in _BASIS_POINT_METRICS and value > _MAX_BASIS_POINTS:
            raise ValueError("basis points must be between 0 and 10000")
        if self.numerator is not None:
            object.__setattr__(
                self,
                "numerator",
                _validate_non_negative_int(self.numerator, "numerator"),
            )
        if self.denominator is not None:
            object.__setattr__(
                self,
                "denominator",
                _validate_non_negative_int(self.denominator, "denominator"),
            )


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    id: UUID
    tenant_id: UUID
    scope: MetricScope
    manager_user_id: UUID | None
    window: MetricWindow
    formula_version: str
    source_watermark: datetime
    computed_at: datetime
    status: MetricSnapshotStatus
    values: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.tenant_id, "tenant_id")
        if not isinstance(self.scope, MetricScope):
            raise TypeError("scope must be a MetricScope")
        if self.scope is MetricScope.TENANT and self.manager_user_id is not None:
            raise ValueError("tenant scope requires manager_user_id to be null")
        if self.scope is MetricScope.MANAGER:
            if self.manager_user_id is None:
                raise ValueError("manager scope requires manager_user_id")
            _validate_uuid(self.manager_user_id, "manager_user_id")
        if not isinstance(self.window, MetricWindow):
            raise TypeError("window must be a MetricWindow")
        object.__setattr__(
            self,
            "formula_version",
            _validate_formula_version(self.formula_version),
        )
        object.__setattr__(
            self,
            "source_watermark",
            _validate_timezone_aware_datetime(self.source_watermark, "source_watermark"),
        )
        object.__setattr__(
            self,
            "computed_at",
            _validate_timezone_aware_datetime(self.computed_at, "computed_at"),
        )
        if not isinstance(self.status, MetricSnapshotStatus):
            raise TypeError("status must be a MetricSnapshotStatus")
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple")
        seen_keys: set[MetricKey] = set()
        for metric_value in self.values:
            if not isinstance(metric_value, MetricValue):
                raise TypeError("values must contain MetricValue entries")
            if metric_value.key in seen_keys:
                raise ValueError("duplicate metric key in snapshot")
            seen_keys.add(metric_value.key)


def floor_basis_points(*, numerator: int, denominator: int) -> int | None:
    if denominator <= 0:
        return None
    return (numerator * 10_000) // denominator


def deterministic_median_seconds(values: tuple[int, ...]) -> int | None:
    if not values:
        return None
    sorted_values = tuple(sorted(values))
    count = len(sorted_values)
    if count % 2 == 1:
        return sorted_values[count // 2]
    lower = sorted_values[(count // 2) - 1]
    upper = sorted_values[count // 2]
    return (lower + upper) // 2


def deterministic_p90_seconds(values: tuple[int, ...]) -> int | None:
    """Nearest-rank p90 on sorted integer seconds."""
    if not values:
        return None
    sorted_values = tuple(sorted(values))
    count = len(sorted_values)
    rank = ((90 * count) + 99) // 100
    index = max(0, min(count - 1, rank - 1))
    return sorted_values[index]
