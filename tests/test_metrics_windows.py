"""Unit tests for tenant-local metric window derivation (Block LM)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from closeros.application.metrics_windows import (
    daily_window_for_local_date,
    local_date_from_timestamp,
    rolling_30_day_window_for_local_date,
)
from closeros.domain.metrics import MetricWindow


def test_daily_window_utc_is_half_open_midnight_interval() -> None:
    local_date = date(2026, 7, 12)
    window = daily_window_for_local_date(local_date=local_date, time_zone="UTC")
    assert window.start == datetime(2026, 7, 12, 0, 0, tzinfo=UTC)
    assert window.end == datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    assert window.end - window.start == timedelta(days=1)
    assert window.window_code == "daily_2026-07-12"


def test_daily_window_almaty_uses_tenant_timezone() -> None:
    local_date = date(2026, 7, 12)
    window = daily_window_for_local_date(local_date=local_date, time_zone="Asia/Almaty")
    zone = ZoneInfo("Asia/Almaty")
    assert window.start == datetime(2026, 7, 12, 0, 0, tzinfo=zone)
    assert window.end == datetime(2026, 7, 13, 0, 0, tzinfo=zone)
    assert window.start.utcoffset() == timedelta(hours=5)


def test_daily_window_new_york_offsets_from_utc() -> None:
    local_date = date(2026, 1, 15)
    window = daily_window_for_local_date(local_date=local_date, time_zone="America/New_York")
    zone = ZoneInfo("America/New_York")
    assert window.start == datetime(2026, 1, 15, 0, 0, tzinfo=zone)
    assert window.end == datetime(2026, 1, 16, 0, 0, tzinfo=zone)
    assert window.start.astimezone(UTC) == datetime(2026, 1, 15, 5, 0, tzinfo=UTC)


def test_rolling_30_day_window_spans_thirty_days() -> None:
    local_date = date(2026, 7, 12)
    window = rolling_30_day_window_for_local_date(local_date=local_date, time_zone="UTC")
    assert window.end - window.start == timedelta(days=30)
    assert window.window_code == "rolling_30d_2026-07-12"


def test_rolling_30_day_window_end_is_next_local_midnight() -> None:
    local_date = date(2026, 7, 12)
    window = rolling_30_day_window_for_local_date(local_date=local_date, time_zone="UTC")
    assert window.end == datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    assert window.start == datetime(2026, 6, 13, 0, 0, tzinfo=UTC)


def test_rolling_30_day_window_almaty_boundaries() -> None:
    local_date = date(2026, 7, 12)
    window = rolling_30_day_window_for_local_date(local_date=local_date, time_zone="Asia/Almaty")
    zone = ZoneInfo("Asia/Almaty")
    assert window.end == datetime(2026, 7, 13, 0, 0, tzinfo=zone)
    assert window.start == datetime(2026, 6, 13, 0, 0, tzinfo=zone)


def test_daily_window_start_inclusive_end_exclusive() -> None:
    window = daily_window_for_local_date(local_date=date(2026, 7, 1), time_zone="UTC")
    assert window.start < window.end
    inclusive = window.start
    exclusive = window.end
    assert inclusive >= window.start and inclusive < window.end
    assert not (exclusive >= window.start and exclusive < window.end)


def test_local_date_from_timestamp_utc() -> None:
    occurred_at = datetime(2026, 7, 12, 15, 30, tzinfo=UTC)
    assert local_date_from_timestamp(occurred_at=occurred_at, time_zone="UTC") == date(2026, 7, 12)


def test_local_date_from_timestamp_crosses_midnight_in_almaty() -> None:
    occurred_at = datetime(2026, 7, 11, 20, 0, tzinfo=UTC)
    assert local_date_from_timestamp(occurred_at=occurred_at, time_zone="Asia/Almaty") == date(
        2026, 7, 12
    )


def test_local_date_from_timestamp_before_midnight_in_almaty() -> None:
    occurred_at = datetime(2026, 7, 11, 18, 59, tzinfo=UTC)
    assert local_date_from_timestamp(occurred_at=occurred_at, time_zone="Asia/Almaty") == date(
        2026, 7, 11
    )


def test_metric_window_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MetricWindow(
            start=datetime(2026, 7, 1, 0, 0),
            end=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            window_code="daily_2026-07-01",
        )


def test_daily_and_rolling_windows_share_end_boundary_for_same_local_date() -> None:
    local_date = date(2026, 7, 12)
    daily = daily_window_for_local_date(local_date=local_date, time_zone="UTC")
    rolling = rolling_30_day_window_for_local_date(local_date=local_date, time_zone="UTC")
    assert daily.end == rolling.end
    assert rolling.start < daily.start
