"""Framework-independent authentication session timeout policy."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from closeros.domain.authentication import AuthenticationSessionStage


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
class AuthenticationSessionTimeoutPolicy:
    authenticated_idle_timeout: timedelta
    authenticated_absolute_timeout: timedelta
    pending_mfa_timeout: timedelta

    def __post_init__(self) -> None:
        _validate_positive_timedelta(
            self.authenticated_idle_timeout,
            "authenticated_idle_timeout",
        )
        _validate_positive_timedelta(
            self.authenticated_absolute_timeout,
            "authenticated_absolute_timeout",
        )
        _validate_positive_timedelta(
            self.pending_mfa_timeout,
            "pending_mfa_timeout",
        )


AUTHENTICATION_SESSION_TIMEOUT_POLICY = AuthenticationSessionTimeoutPolicy(
    authenticated_idle_timeout=timedelta(minutes=30),
    authenticated_absolute_timeout=timedelta(hours=12),
    pending_mfa_timeout=timedelta(minutes=5),
)


def calculate_authentication_session_absolute_expiry(
    *,
    stage: AuthenticationSessionStage,
    created_at: datetime,
    policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> datetime:
    if not isinstance(stage, AuthenticationSessionStage):
        raise TypeError("stage must be an AuthenticationSessionStage")

    validated_created_at = _validate_timezone_aware_datetime(
        created_at,
        "created_at",
    )

    if not isinstance(policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("policy must be an AuthenticationSessionTimeoutPolicy")

    if stage is AuthenticationSessionStage.PENDING_MFA:
        return validated_created_at + policy.pending_mfa_timeout

    return validated_created_at + policy.authenticated_absolute_timeout


def calculate_authentication_session_idle_expiry(
    *,
    stage: AuthenticationSessionStage,
    last_seen_at: datetime,
    policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> datetime | None:
    if not isinstance(stage, AuthenticationSessionStage):
        raise TypeError("stage must be an AuthenticationSessionStage")

    validated_last_seen_at = _validate_timezone_aware_datetime(
        last_seen_at,
        "last_seen_at",
    )

    if not isinstance(policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("policy must be an AuthenticationSessionTimeoutPolicy")

    if stage is AuthenticationSessionStage.PENDING_MFA:
        return None

    return validated_last_seen_at + policy.authenticated_idle_timeout
