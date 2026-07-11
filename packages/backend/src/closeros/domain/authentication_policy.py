"""Framework-independent privileged-role MFA policy."""

from closeros.domain.authentication import AuthenticationAssuranceLevel
from closeros.domain.authentication_session import AuthenticationSession
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
