"""Freshness evaluation for catalog commercial facts."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from closeros.domain.product_catalog import (
    FactProvenance,
    FactVerificationStatus,
    is_usable_verification_status,
)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


def evaluate_fact_freshness(
    *,
    verification_status: FactVerificationStatus,
    source_updated_at: datetime,
    checked_at: datetime | None,
    ttl_seconds: int,
    now: datetime,
    source_id: UUID,
) -> FactProvenance:
    """Determine whether a fact may be stated as confirmed to a customer."""
    now = _ensure_aware(now)
    source_updated_at = _ensure_aware(source_updated_at)
    if checked_at is not None:
        checked_at = _ensure_aware(checked_at)

    if verification_status is FactVerificationStatus.UNVERIFIED:
        return FactProvenance(
            source_id=source_id,
            source_updated_at=source_updated_at,
            verification_status=verification_status,
            checked_at=checked_at,
            usable=False,
            valid_until=None,
        )

    if verification_status is FactVerificationStatus.STALE:
        return FactProvenance(
            source_id=source_id,
            source_updated_at=source_updated_at,
            verification_status=verification_status,
            checked_at=checked_at,
            usable=False,
            valid_until=None,
        )

    if verification_status is FactVerificationStatus.LIVE:
        return FactProvenance(
            source_id=source_id,
            source_updated_at=source_updated_at,
            verification_status=verification_status,
            checked_at=checked_at,
            usable=True,
            valid_until=None,
        )

    # verified / synced: usable within TTL from source_updated_at (or checked_at if newer)
    anchor = source_updated_at
    if checked_at is not None and checked_at > anchor:
        anchor = checked_at
    valid_until = anchor + timedelta(seconds=ttl_seconds)
    usable = is_usable_verification_status(verification_status) and now <= valid_until
    effective_status = verification_status if usable else FactVerificationStatus.STALE
    return FactProvenance(
        source_id=source_id,
        source_updated_at=source_updated_at,
        verification_status=effective_status,
        checked_at=checked_at,
        usable=usable,
        valid_until=valid_until,
    )


def default_freshness_policy_values() -> dict[str, int]:
    from closeros.domain.product_catalog import (
        DEFAULT_DELIVERY_TTL,
        DEFAULT_DESCRIPTION_TTL,
        DEFAULT_INVENTORY_TTL,
        DEFAULT_PRICE_TTL,
        DEFAULT_PROMOTION_TTL,
    )

    return {
        "inventory_ttl_seconds": int(DEFAULT_INVENTORY_TTL.total_seconds()),
        "price_ttl_seconds": int(DEFAULT_PRICE_TTL.total_seconds()),
        "delivery_ttl_seconds": int(DEFAULT_DELIVERY_TTL.total_seconds()),
        "promotion_ttl_seconds": int(DEFAULT_PROMOTION_TTL.total_seconds()),
        "description_ttl_seconds": int(DEFAULT_DESCRIPTION_TTL.total_seconds()),
    }
