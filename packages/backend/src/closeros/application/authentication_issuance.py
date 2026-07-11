"""Application services for authentication session and token issuance."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
)
from closeros.domain.authentication_policy import (
    require_usable_authentication_session,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_timeout import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionTimeoutPolicy,
    calculate_authentication_session_absolute_expiry,
)
from closeros.domain.authentication_token import (
    AuthenticationOneTimeToken,
)
from closeros.domain.authentication_token_timeout import (
    AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY,
    AuthenticationOneTimeTokenTimeoutPolicy,
    calculate_authentication_one_time_token_expiry,
)
from closeros.security.authentication_tokens import (
    RawAuthenticationToken,
    generate_raw_authentication_token,
    hash_authentication_token,
)

_RawAuthenticationTokenFactory = Callable[
    [],
    RawAuthenticationToken,
]


def _validate_uuid(
    value: object,
    field_name: str,
) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")

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


def _generate_raw_token_and_hash(
    raw_token_factory: _RawAuthenticationTokenFactory,
) -> tuple[RawAuthenticationToken, AuthenticationTokenHash]:
    if not callable(raw_token_factory):
        raise TypeError("raw_token_factory must be callable")

    raw_token = raw_token_factory()

    if not isinstance(raw_token, RawAuthenticationToken):
        raise TypeError("raw_token_factory must return a RawAuthenticationToken")

    return raw_token, hash_authentication_token(raw_token)


@dataclass(frozen=True, slots=True)
class IssuedAuthenticationSession:
    session: AuthenticationSession
    raw_token: RawAuthenticationToken = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.session, AuthenticationSession):
            raise TypeError("session must be an AuthenticationSession")

        if not isinstance(self.raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")


@dataclass(frozen=True, slots=True)
class IssuedAuthenticationOneTimeToken:
    token: AuthenticationOneTimeToken
    raw_token: RawAuthenticationToken = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(
            self.token,
            AuthenticationOneTimeToken,
        ):
            raise TypeError("token must be an AuthenticationOneTimeToken")

        if not isinstance(self.raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")


@dataclass(frozen=True, slots=True)
class AuthenticationSessionRotation:
    revoked_session: AuthenticationSession
    issued: IssuedAuthenticationSession

    def __post_init__(self) -> None:
        if not isinstance(
            self.revoked_session,
            AuthenticationSession,
        ):
            raise TypeError("revoked_session must be an AuthenticationSession")

        if not isinstance(
            self.issued,
            IssuedAuthenticationSession,
        ):
            raise TypeError("issued must be an IssuedAuthenticationSession")


class AuthenticationSessionTransitionError(PermissionError):
    """Raised when an authentication session transition is unavailable."""


def issue_pending_mfa_session(
    *,
    session_id: UUID,
    user_id: UUID,
    issued_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    timeout_policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> IssuedAuthenticationSession:
    validated_session_id = _validate_uuid(session_id, "session_id")
    validated_user_id = _validate_uuid(user_id, "user_id")
    validated_issued_at = _validate_timezone_aware_datetime(
        issued_at,
        "issued_at",
    )

    if not isinstance(timeout_policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("timeout_policy must be an AuthenticationSessionTimeoutPolicy")

    raw_token, token_hash = _generate_raw_token_and_hash(raw_token_factory)

    expires_at = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.PENDING_MFA,
        created_at=validated_issued_at,
        policy=timeout_policy,
    )

    session = AuthenticationSession(
        id=validated_session_id,
        user_id=validated_user_id,
        token_hash=token_hash,
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
        created_at=validated_issued_at,
        last_seen_at=validated_issued_at,
        expires_at=expires_at,
        revoked_at=None,
    )

    return IssuedAuthenticationSession(session=session, raw_token=raw_token)


def issue_authenticated_session(
    *,
    session_id: UUID,
    user_id: UUID,
    assurance_level: AuthenticationAssuranceLevel,
    issued_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    timeout_policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> IssuedAuthenticationSession:
    validated_session_id = _validate_uuid(session_id, "session_id")
    validated_user_id = _validate_uuid(user_id, "user_id")

    if not isinstance(assurance_level, AuthenticationAssuranceLevel):
        raise TypeError("assurance_level must be an AuthenticationAssuranceLevel")

    validated_issued_at = _validate_timezone_aware_datetime(
        issued_at,
        "issued_at",
    )

    if not isinstance(timeout_policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("timeout_policy must be an AuthenticationSessionTimeoutPolicy")

    raw_token, token_hash = _generate_raw_token_and_hash(raw_token_factory)

    mfa_completed = assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR

    expires_at = calculate_authentication_session_absolute_expiry(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        created_at=validated_issued_at,
        policy=timeout_policy,
    )

    session = AuthenticationSession(
        id=validated_session_id,
        user_id=validated_user_id,
        token_hash=token_hash,
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=assurance_level,
        mfa_completed=mfa_completed,
        created_at=validated_issued_at,
        last_seen_at=validated_issued_at,
        expires_at=expires_at,
        revoked_at=None,
    )

    return IssuedAuthenticationSession(session=session, raw_token=raw_token)


def issue_authentication_one_time_token(
    *,
    token_id: UUID,
    user_id: UUID,
    purpose: AuthenticationTokenPurpose,
    issued_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    timeout_policy: AuthenticationOneTimeTokenTimeoutPolicy = (
        AUTHENTICATION_ONE_TIME_TOKEN_TIMEOUT_POLICY
    ),
) -> IssuedAuthenticationOneTimeToken:
    validated_token_id = _validate_uuid(token_id, "token_id")
    validated_user_id = _validate_uuid(user_id, "user_id")

    if not isinstance(purpose, AuthenticationTokenPurpose):
        raise TypeError("purpose must be an AuthenticationTokenPurpose")

    validated_issued_at = _validate_timezone_aware_datetime(
        issued_at,
        "issued_at",
    )

    if not isinstance(
        timeout_policy,
        AuthenticationOneTimeTokenTimeoutPolicy,
    ):
        raise TypeError("timeout_policy must be an AuthenticationOneTimeTokenTimeoutPolicy")

    raw_token, token_hash = _generate_raw_token_and_hash(raw_token_factory)

    expires_at = calculate_authentication_one_time_token_expiry(
        purpose=purpose,
        created_at=validated_issued_at,
        policy=timeout_policy,
    )

    token = AuthenticationOneTimeToken(
        id=validated_token_id,
        user_id=validated_user_id,
        purpose=purpose,
        token_hash=token_hash,
        created_at=validated_issued_at,
        expires_at=expires_at,
        consumed_at=None,
        revoked_at=None,
    )

    return IssuedAuthenticationOneTimeToken(token=token, raw_token=raw_token)


def complete_pending_mfa_and_rotate_session(
    *,
    pending_session: AuthenticationSession,
    new_session_id: UUID,
    completed_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    timeout_policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> AuthenticationSessionRotation:
    if not isinstance(pending_session, AuthenticationSession):
        raise TypeError("pending_session must be an AuthenticationSession")

    validated_new_session_id = _validate_uuid(new_session_id, "new_session_id")
    validated_completed_at = _validate_timezone_aware_datetime(
        completed_at,
        "completed_at",
    )

    if not isinstance(timeout_policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("timeout_policy must be an AuthenticationSessionTimeoutPolicy")

    if pending_session.stage is not AuthenticationSessionStage.PENDING_MFA:
        raise AuthenticationSessionTransitionError("authentication session transition unavailable")

    if validated_new_session_id == pending_session.id:
        raise AuthenticationSessionTransitionError("authentication session transition unavailable")

    require_usable_authentication_session(
        session=pending_session,
        now=validated_completed_at,
        policy=timeout_policy,
    )

    revoked_session = replace(
        pending_session,
        revoked_at=validated_completed_at,
    )

    issued = issue_authenticated_session(
        session_id=validated_new_session_id,
        user_id=pending_session.user_id,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=validated_completed_at,
        raw_token_factory=raw_token_factory,
        timeout_policy=timeout_policy,
    )

    return AuthenticationSessionRotation(
        revoked_session=revoked_session,
        issued=issued,
    )


__all__ = [
    "AuthenticationSessionRotation",
    "AuthenticationSessionTransitionError",
    "IssuedAuthenticationOneTimeToken",
    "IssuedAuthenticationSession",
    "complete_pending_mfa_and_rotate_session",
    "issue_authenticated_session",
    "issue_authentication_one_time_token",
    "issue_pending_mfa_session",
]
