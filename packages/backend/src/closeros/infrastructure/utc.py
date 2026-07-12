"""UTC-aware timestamp validation for persistence boundaries."""

from __future__ import annotations

from datetime import datetime


def require_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return dt
