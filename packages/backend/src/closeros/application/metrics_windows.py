"""Explicit metric windows derived from tenant-local calendar dates."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from closeros.domain.metrics import MetricWindow


def _local_midnight(value: date, time_zone: str) -> datetime:
    zone = ZoneInfo(time_zone)
    return datetime.combine(value, time.min, tzinfo=zone)


def daily_window_for_local_date(*, local_date: date, time_zone: str) -> MetricWindow:
    start = _local_midnight(local_date, time_zone)
    end = start + timedelta(days=1)
    return MetricWindow(
        start=start,
        end=end,
        window_code=f"daily_{local_date.isoformat()}",
    )


def rolling_30_day_window_for_local_date(*, local_date: date, time_zone: str) -> MetricWindow:
    end = _local_midnight(local_date, time_zone) + timedelta(days=1)
    start = end - timedelta(days=30)
    return MetricWindow(
        start=start,
        end=end,
        window_code=f"rolling_30d_{local_date.isoformat()}",
    )


def local_date_from_timestamp(*, occurred_at: datetime, time_zone: str) -> date:
    return occurred_at.astimezone(ZoneInfo(time_zone)).date()
