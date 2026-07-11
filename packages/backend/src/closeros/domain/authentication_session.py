"""Framework-independent authentication session domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
)

_PENDING_MFA_COMBINATION_ERROR = (
    "pending MFA session must use single-factor assurance with incomplete MFA"
)
_AUTHENTICATED_MFA_STATE_ERROR = "authenticated session MFA state must match assurance level"


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(slots=True)
class AuthenticationSession:
    id: UUID
    user_id: UUID
    token_hash: AuthenticationTokenHash = field(repr=False)
    stage: AuthenticationSessionStage
    assurance_level: AuthenticationAssuranceLevel
    mfa_completed: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.user_id, UUID):
            raise TypeError("user_id must be a UUID")

        if not isinstance(self.token_hash, AuthenticationTokenHash):
            raise TypeError("token_hash must be an AuthenticationTokenHash")

        if not isinstance(self.stage, AuthenticationSessionStage):
            raise TypeError("stage must be an AuthenticationSessionStage")

        if not isinstance(self.assurance_level, AuthenticationAssuranceLevel):
            raise TypeError("assurance_level must be an AuthenticationAssuranceLevel")

        if type(self.mfa_completed) is not bool:
            raise TypeError("mfa_completed must be a bool")

        if self.stage is AuthenticationSessionStage.PENDING_MFA:
            if (
                self.assurance_level is not AuthenticationAssuranceLevel.SINGLE_FACTOR
                or self.mfa_completed is not False
            ):
                raise ValueError(_PENDING_MFA_COMBINATION_ERROR)
        elif self.stage is AuthenticationSessionStage.AUTHENTICATED:
            if (
                self.assurance_level is AuthenticationAssuranceLevel.SINGLE_FACTOR
                and self.mfa_completed is not False
            ):
                raise ValueError(_AUTHENTICATED_MFA_STATE_ERROR)
            if (
                self.assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR
                and self.mfa_completed is not True
            ):
                raise ValueError(_AUTHENTICATED_MFA_STATE_ERROR)

        created_at = _validate_timezone_aware_datetime(self.created_at, "created_at")
        last_seen_at = _validate_timezone_aware_datetime(self.last_seen_at, "last_seen_at")
        expires_at = _validate_timezone_aware_datetime(self.expires_at, "expires_at")

        if self.revoked_at is not None:
            if not isinstance(self.revoked_at, datetime):
                raise TypeError("revoked_at must be a datetime")

            revoked_at = _validate_timezone_aware_datetime(self.revoked_at, "revoked_at")
        else:
            revoked_at = None

        if last_seen_at < created_at:
            raise ValueError("last_seen_at must be greater than or equal to created_at")

        if expires_at <= created_at:
            raise ValueError("expires_at must be strictly greater than created_at")

        if last_seen_at > expires_at:
            raise ValueError("last_seen_at must be less than or equal to expires_at")

        if revoked_at is not None and revoked_at < created_at:
            raise ValueError("revoked_at must be greater than or equal to created_at")
