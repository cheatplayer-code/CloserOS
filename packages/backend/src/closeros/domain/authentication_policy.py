"""Framework-independent authentication policy guards."""

from datetime import datetime

from closeros.domain.authentication import AuthenticationAssuranceLevel
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_timeout import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionTimeoutPolicy,
    calculate_authentication_session_absolute_expiry,
    calculate_authentication_session_idle_expiry,
)
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import Role
from closeros.domain.membership import Membership

_PRIVILEGED_MFA_ROLES: frozenset[Role] = frozenset(
    {
        Role.OWNER,
        Role.SALES_HEAD,
        Role.COMPLIANCE_ADMIN,
    }
)


class MfaRequiredError(PermissionError):
    """Raised when privileged access requires completed MFA."""


class EmailVerificationRequiredError(PermissionError):
    """Raised when authentication requires a verified email."""


class AuthenticationTokenUnavailableError(PermissionError):
    """Raised when a one-time authentication token cannot be used."""


class AuthenticationSessionUnavailableError(PermissionError):
    """Raised when an authentication session cannot be used."""


def requires_mfa_for_roles(roles: frozenset[Role]) -> bool:
    if not isinstance(roles, frozenset):
        raise TypeError("roles must be a frozenset")

    if any(not isinstance(role, Role) for role in roles):
        raise TypeError("roles must contain only Role values")

    return not _PRIVILEGED_MFA_ROLES.isdisjoint(roles)


def require_privileged_mfa(
    *,
    membership: Membership,
    session: AuthenticationSession,
) -> None:
    if not isinstance(membership, Membership):
        raise TypeError("membership must be a Membership")

    if not isinstance(session, AuthenticationSession):
        raise TypeError("session must be an AuthenticationSession")

    if membership.user_id != session.user_id:
        raise MfaRequiredError("multi-factor authentication required")

    if not requires_mfa_for_roles(membership.roles):
        return

    if (
        session.assurance_level is not AuthenticationAssuranceLevel.MULTI_FACTOR
        or session.mfa_completed is not True
    ):
        raise MfaRequiredError("multi-factor authentication required")


def require_verified_email(
    *,
    credential: EmailPasswordCredential,
) -> None:
    if not isinstance(credential, EmailPasswordCredential):
        raise TypeError("credential must be an EmailPasswordCredential")

    if credential.email_verified_at is None:
        raise EmailVerificationRequiredError("email verification required")


def require_usable_authentication_token(
    *,
    token: AuthenticationOneTimeToken,
    now: datetime,
) -> None:
    if not isinstance(token, AuthenticationOneTimeToken):
        raise TypeError("token must be an AuthenticationOneTimeToken")

    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if (
        now < token.created_at
        or now >= token.expires_at
        or token.consumed_at is not None
        or token.revoked_at is not None
    ):
        raise AuthenticationTokenUnavailableError("authentication token unavailable")


def require_usable_authentication_session(
    *,
    session: AuthenticationSession,
    now: datetime,
    policy: AuthenticationSessionTimeoutPolicy = (AUTHENTICATION_SESSION_TIMEOUT_POLICY),
) -> None:
    if not isinstance(session, AuthenticationSession):
        raise TypeError("session must be an AuthenticationSession")

    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if not isinstance(policy, AuthenticationSessionTimeoutPolicy):
        raise TypeError("policy must be an AuthenticationSessionTimeoutPolicy")

    absolute_expiry = calculate_authentication_session_absolute_expiry(
        stage=session.stage,
        created_at=session.created_at,
        policy=policy,
    )
    idle_expiry = calculate_authentication_session_idle_expiry(
        stage=session.stage,
        last_seen_at=session.last_seen_at,
        policy=policy,
    )

    if (
        now < session.created_at
        or now < session.last_seen_at
        or now >= session.expires_at
        or now >= absolute_expiry
        or (idle_expiry is not None and now >= idle_expiry)
        or session.revoked_at is not None
    ):
        raise AuthenticationSessionUnavailableError("authentication session unavailable")
