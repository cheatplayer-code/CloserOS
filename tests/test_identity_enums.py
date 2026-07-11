"""Tests for CLS-010.1 identity domain enums."""

# mypy: disable-error-code=import-untyped

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
    assert Role.OWNER.value == "owner"
    assert Role.SALES_HEAD.value == "sales_head"
    assert Role.MANAGER.value == "manager"
    assert Role.ANALYST.value == "analyst"
    assert Role.COMPLIANCE_ADMIN.value == "compliance_admin"
    assert set(Role) == {
        Role.OWNER,
        Role.SALES_HEAD,
        Role.MANAGER,
        Role.ANALYST,
        Role.COMPLIANCE_ADMIN,
    }


def test_tenant_status_exact_values() -> None:
    assert TenantStatus.ACTIVE.value == "active"
    assert TenantStatus.SUSPENDED.value == "suspended"
    assert set(TenantStatus) == {TenantStatus.ACTIVE, TenantStatus.SUSPENDED}


def test_user_status_exact_values() -> None:
    assert UserStatus.ACTIVE.value == "active"
    assert UserStatus.DISABLED.value == "disabled"
    assert set(UserStatus) == {UserStatus.ACTIVE, UserStatus.DISABLED}


def test_membership_status_exact_values() -> None:
    assert MembershipStatus.ACTIVE.value == "active"
    assert MembershipStatus.SUSPENDED.value == "suspended"
    assert MembershipStatus.REMOVED.value == "removed"
    assert set(MembershipStatus) == {
        MembershipStatus.ACTIVE,
        MembershipStatus.SUSPENDED,
        MembershipStatus.REMOVED,
    }


def test_invitation_status_exact_values() -> None:
    assert InvitationStatus.PENDING.value == "pending"
    assert InvitationStatus.ACCEPTED.value == "accepted"
    assert InvitationStatus.EXPIRED.value == "expired"
    assert InvitationStatus.REVOKED.value == "revoked"
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
            assert str(member) == member.value


def test_enum_values_are_unique() -> None:
    for enum_cls in _IDENTITY_ENUMS:
        values = [member.value for member in enum_cls]
        assert len(values) == len(set(values))
