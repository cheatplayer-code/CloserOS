"""Framework-independent email/password credential domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from closeros.domain.authentication import AuthenticationEmail, PasswordHash


def _validate_timezone_aware_datetime(
    value: object,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(slots=True)
class EmailPasswordCredential:
    id: UUID
    user_id: UUID
    email: AuthenticationEmail = field(repr=False)
    password_hash: PasswordHash = field(repr=False)
    created_at: datetime
    email_verified_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.user_id, UUID):
            raise TypeError("user_id must be a UUID")

        if not isinstance(self.email, AuthenticationEmail):
            raise TypeError("email must be an AuthenticationEmail")

        if not isinstance(self.password_hash, PasswordHash):
            raise TypeError("password_hash must be a PasswordHash")

        created_at = _validate_timezone_aware_datetime(
            self.created_at,
            "created_at",
        )

        if self.email_verified_at is not None:
            email_verified_at = _validate_timezone_aware_datetime(
                self.email_verified_at,
                "email_verified_at",
            )

            if email_verified_at < created_at:
                raise ValueError("email_verified_at must be greater than or equal to created_at")
