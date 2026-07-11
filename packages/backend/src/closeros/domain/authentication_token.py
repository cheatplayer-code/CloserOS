"""Framework-independent one-time authentication token domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from closeros.domain.authentication import (
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
)


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(slots=True)
class AuthenticationOneTimeToken:
    id: UUID
    user_id: UUID
    purpose: AuthenticationTokenPurpose
    token_hash: AuthenticationTokenHash = field(repr=False)
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.user_id, UUID):
            raise TypeError("user_id must be a UUID")

        if not isinstance(self.purpose, AuthenticationTokenPurpose):
            raise TypeError("purpose must be an AuthenticationTokenPurpose")

        if not isinstance(self.token_hash, AuthenticationTokenHash):
            raise TypeError("token_hash must be an AuthenticationTokenHash")

        created_at = _validate_timezone_aware_datetime(self.created_at, "created_at")
        expires_at = _validate_timezone_aware_datetime(self.expires_at, "expires_at")

        if self.consumed_at is not None:
            if not isinstance(self.consumed_at, datetime):
                raise TypeError("consumed_at must be a datetime")

            consumed_at = _validate_timezone_aware_datetime(self.consumed_at, "consumed_at")
        else:
            consumed_at = None

        if self.revoked_at is not None:
            if not isinstance(self.revoked_at, datetime):
                raise TypeError("revoked_at must be a datetime")

            revoked_at = _validate_timezone_aware_datetime(self.revoked_at, "revoked_at")
        else:
            revoked_at = None

        if expires_at <= created_at:
            raise ValueError("expires_at must be strictly greater than created_at")

        if consumed_at is not None and consumed_at < created_at:
            raise ValueError("consumed_at must be greater than or equal to created_at")

        if consumed_at is not None and consumed_at > expires_at:
            raise ValueError("consumed_at must be less than or equal to expires_at")

        if revoked_at is not None and revoked_at < created_at:
            raise ValueError("revoked_at must be greater than or equal to created_at")
