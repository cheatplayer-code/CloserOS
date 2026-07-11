"""Tests for CLS-010.2c membership domain entity."""

from uuid import UUID

import pytest
from closeros.domain import Membership
from closeros.domain.identity import MembershipStatus, Role, UserStatus

MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000020")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
MANAGER_ROLES = frozenset({Role.MANAGER})


def test_valid_membership_stores_ids_roles_and_active_status() -> None:
    membership = Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        roles=MANAGER_ROLES,
        status=MembershipStatus.ACTIVE,
    )

    assert membership.id == MEMBERSHIP_ID
    assert membership.tenant_id == TENANT_ID
    assert membership.user_id == USER_ID
    assert membership.roles == MANAGER_ROLES
    assert membership.status is MembershipStatus.ACTIVE


def test_suspended_status_is_accepted() -> None:
    membership = Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        roles=MANAGER_ROLES,
        status=MembershipStatus.SUSPENDED,
    )

    assert membership.status is MembershipStatus.SUSPENDED


def test_removed_status_is_accepted() -> None:
    membership = Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        roles=MANAGER_ROLES,
        status=MembershipStatus.REMOVED,
    )

    assert membership.status is MembershipStatus.REMOVED


def test_multiple_valid_roles_are_accepted() -> None:
    roles = frozenset({Role.OWNER, Role.MANAGER, Role.ANALYST})
    membership = Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        roles=roles,
        status=MembershipStatus.ACTIVE,
    )

    assert membership.roles == roles


def test_empty_roles_raise_value_error() -> None:
    with pytest.raises(ValueError, match="roles must not be empty"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles=frozenset(),
            status=MembershipStatus.ACTIVE,
        )


def test_set_roles_raise_type_error() -> None:
    with pytest.raises(TypeError, match="roles must be a frozenset"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles={Role.MANAGER},  # type: ignore[arg-type]
            status=MembershipStatus.ACTIVE,
        )


def test_frozenset_with_string_role_raises_type_error() -> None:
    with pytest.raises(TypeError, match="roles must contain only Role values"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles=frozenset({"manager"}),  # type: ignore[arg-type]
            status=MembershipStatus.ACTIVE,
        )


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        Membership(
            id=123,  # type: ignore[arg-type]
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles=MANAGER_ROLES,
            status=MembershipStatus.ACTIVE,
        )


def test_non_uuid_tenant_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="tenant_id must be a UUID"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
            user_id=USER_ID,
            roles=MANAGER_ROLES,
            status=MembershipStatus.ACTIVE,
        )


def test_non_uuid_user_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=123,  # type: ignore[arg-type]
            roles=MANAGER_ROLES,
            status=MembershipStatus.ACTIVE,
        )


def test_plain_string_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be a MembershipStatus"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles=MANAGER_ROLES,
            status="active",  # type: ignore[arg-type]
        )


def test_user_status_used_as_membership_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be a MembershipStatus"):
        Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            roles=MANAGER_ROLES,
            status=UserStatus.ACTIVE,  # type: ignore[arg-type]
        )


def test_membership_can_be_imported_from_closeros_domain() -> None:
    assert Membership.__name__ == "Membership"
