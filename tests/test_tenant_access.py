"""Tests for CLS-010.3a tenant access guard."""

from uuid import UUID

import pytest
from closeros.domain import (
    Membership,
    Tenant,
    TenantAccessDeniedError,
    User,
    require_tenant_access,
)
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000011")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000020")
DENIED_MESSAGE = "tenant access denied"
MANAGER_ROLES = frozenset({Role.MANAGER})


def _active_tenant(*, tenant_id: UUID = TENANT_ID) -> Tenant:
    return Tenant(id=tenant_id, name="Acme Corp", status=TenantStatus.ACTIVE)


def _active_user(*, user_id: UUID = USER_ID) -> User:
    return User(id=user_id, status=UserStatus.ACTIVE)


def _active_membership(
    *,
    tenant_id: UUID = TENANT_ID,
    user_id: UUID = USER_ID,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    return Membership(
        id=MEMBERSHIP_ID,
        tenant_id=tenant_id,
        user_id=user_id,
        roles=MANAGER_ROLES,
        status=status,
    )


def test_active_matching_membership_is_allowed() -> None:
    result = require_tenant_access(
        tenant=_active_tenant(),
        user=_active_user(),
        membership=_active_membership(),
    )

    assert result is None


def test_membership_for_another_tenant_is_denied() -> None:
    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=_active_tenant(),
            user=_active_user(),
            membership=_active_membership(tenant_id=OTHER_TENANT_ID),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_membership_for_another_user_is_denied() -> None:
    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=_active_tenant(),
            user=_active_user(),
            membership=_active_membership(user_id=OTHER_USER_ID),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_suspended_tenant_is_denied() -> None:
    tenant = Tenant(id=TENANT_ID, name="Acme Corp", status=TenantStatus.SUSPENDED)

    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=tenant,
            user=_active_user(),
            membership=_active_membership(),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_disabled_user_is_denied() -> None:
    user = User(id=USER_ID, status=UserStatus.DISABLED)

    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=_active_tenant(),
            user=user,
            membership=_active_membership(),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_suspended_membership_is_denied() -> None:
    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=_active_tenant(),
            user=_active_user(),
            membership=_active_membership(status=MembershipStatus.SUSPENDED),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_removed_membership_is_denied() -> None:
    with pytest.raises(TenantAccessDeniedError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_tenant_access(
            tenant=_active_tenant(),
            user=_active_user(),
            membership=_active_membership(status=MembershipStatus.REMOVED),
        )

    assert str(exc_info.value) == DENIED_MESSAGE


def test_wrong_tenant_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="tenant must be a Tenant"):
        require_tenant_access(
            tenant="tenant",  # type: ignore[arg-type]
            user=_active_user(),
            membership=_active_membership(),
        )


def test_wrong_user_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="user must be a User"):
        require_tenant_access(
            tenant=_active_tenant(),
            user="user",  # type: ignore[arg-type]
            membership=_active_membership(),
        )


def test_wrong_membership_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="membership must be a Membership"):
        require_tenant_access(
            tenant=_active_tenant(),
            user=_active_user(),
            membership="membership",  # type: ignore[arg-type]
        )


def test_access_guard_exports_are_available_from_closeros_domain() -> None:
    assert TenantAccessDeniedError.__name__ == "TenantAccessDeniedError"
    assert require_tenant_access.__name__ == "require_tenant_access"
    assert issubclass(TenantAccessDeniedError, PermissionError)
