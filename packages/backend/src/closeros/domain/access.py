"""Framework-independent tenant access guard."""

from closeros.domain.identity import MembershipStatus, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant
from closeros.domain.user import User

TENANT_ACCESS_DENIED_MESSAGE = "tenant access denied"


class TenantAccessDeniedError(PermissionError):
    """Raised when tenant access preconditions are not satisfied."""


def require_tenant_access(
    *,
    tenant: Tenant,
    user: User,
    membership: Membership,
) -> None:
    if not isinstance(tenant, Tenant):
        raise TypeError("tenant must be a Tenant")

    if not isinstance(user, User):
        raise TypeError("user must be a User")

    if not isinstance(membership, Membership):
        raise TypeError("membership must be a Membership")

    if (
        tenant.status is TenantStatus.ACTIVE
        and user.status is UserStatus.ACTIVE
        and membership.status is MembershipStatus.ACTIVE
        and membership.tenant_id == tenant.id
        and membership.user_id == user.id
    ):
        return None

    raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
