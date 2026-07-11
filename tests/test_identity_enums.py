"""Tests for CLS-010.1 identity domain enums."""

from enum import StrEnum

from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
    UserStatus,
)

_IDENTITY_ENUMS: tuple[type[StrEnum], ...] = (
    Role,
    TenantStatus,
    UserStatus,
    MembershipStatus,
    InvitationStatus,
)


def test_role_exact_values() -> None:
    assert Role.OWNER == "owner"
    assert Role.SALES_HEAD == "sales_head"
    assert Role.MANAGER == "manager"
    assert Role.ANALYST == "analyst"
    assert Role.COMPLIANCE_ADMIN == "compliance_admin"
    assert set(Role) == {
        Role.OWNER,
        Role.SALES_HEAD,
        Role.MANAGER,
        Role.ANALYST,
        Role.COMPLIANCE_ADMIN,
    }


def test_tenant_status_exact_values() -> None:
    assert TenantStatus.ACTIVE == "active"
    assert TenantStatus.SUSPENDED == "suspended"
    assert set(TenantStatus) == {TenantStatus.ACTIVE, TenantStatus.SUSPENDED}


def test_user_status_exact_values() -> None:
    assert UserStatus.ACTIVE == "active"
    assert UserStatus.DISABLED == "disabled"
    assert set(UserStatus) == {UserStatus.ACTIVE, UserStatus.DISABLED}


def test_membership_status_exact_values() -> None:
    assert MembershipStatus.ACTIVE == "active"
    assert MembershipStatus.SUSPENDED == "suspended"
    assert MembershipStatus.REMOVED == "removed"
    assert set(MembershipStatus) == {
        MembershipStatus.ACTIVE,
        MembershipStatus.SUSPENDED,
        MembershipStatus.REMOVED,
    }


def test_invitation_status_exact_values() -> None:
    assert InvitationStatus.PENDING == "pending"
    assert InvitationStatus.ACCEPTED == "accepted"
    assert InvitationStatus.EXPIRED == "expired"
    assert InvitationStatus.REVOKED == "revoked"
    assert set(InvitationStatus) == {
        InvitationStatus.PENDING,
        InvitationStatus.ACCEPTED,
        InvitationStatus.EXPIRED,
        InvitationStatus.REVOKED,
    }


def test_enum_members_behave_as_strings() -> None:
    for enum_cls in _IDENTITY_ENUMS:
        for member in enum_cls:
            assert isinstance(member, str)
            assert member == str(member)
            assert member == member.value


def test_enum_values_are_unique() -> None:
    for enum_cls in _IDENTITY_ENUMS:
        values = [member.value for member in enum_cls]
        assert len(values) == len(set(values))
