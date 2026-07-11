"""Framework-independent one-time authentication token timeout policy."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from closeros.domain.authentication import AuthenticationTokenPurpose


def _validate_positive_timedelta(
    value: object,
    field_name: str,
) -> timedelta:
    if not isinstance(value, timedelta):
        raise TypeError(f"{field_name} must be a timedelta")

    if value <= timedelta(0):
        raise ValueError(f"{field_name} must be greater than zero")

    return value


def _validate_timezone_aware_datetime(
    value: object,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


@dataclass(frozen=True, slots=True)
class AuthenticationOneTimeTokenTimeoutPolicy:
    email_verification_timeout: timedelta
    password_reset_timeout: timedelta

    def __post_init__(self) -> None:
        _validate_positive_timedelta(
            self.email_verification_timeout,
            "email_verification_timeout",
        )
        _validate_positive_timedelta(
            self.password_reset_timeout,
            "password_reset_timeout",
        )


AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY = AuthenticationOneTimeTokenTimeoutPolicy(
    email_verification_timeout=timedelta(hours=24),
    password_reset_timeout=timedelta(minutes=30),
)


def calculate_authentication_one_time_token_expiry(
    *,
    purpose: AuthenticationTokenPurpose,
    created_at: datetime,
    policy: AuthenticationOneTimeTokenTimeoutPolicy = (
        AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY
    ),
) -> datetime:
    if not isinstance(purpose, AuthenticationTokenPurpose):
        raise TypeError("purpose must be an AuthenticationTokenPurpose")

    validated_created_at = _validate_timezone_aware_datetime(
        created_at,
        "created_at",
    )

    if not isinstance(
        policy,
        AuthenticationOneTimeTokenTimeoutPolicy,
    ):
        raise TypeError("policy must be an AuthenticationOneTimeTokenTimeoutPolicy")

    if purpose is AuthenticationTokenPurpose.EMAIL_VERIFICATION:
        return validated_created_at + policy.email_verification_timeout

    return validated_created_at + policy.password_reset_timeout
