"""Tests for CLS-010.2d invitation domain entity."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import Invitation
from closeros.domain.identity import InvitationStatus, MembershipStatus, Role

INVITATION_ID = UUID("00000000-0000-0000-0000-000000000030")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
EXPIRES_AT = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
MANAGER_ROLES = frozenset({Role.MANAGER})


def _build_invitation(**overrides: object) -> Invitation:
    values = {
        "id": INVITATION_ID,
        "tenant_id": TENANT_ID,
        "email": "Manager@Example.COM",
        "roles": MANAGER_ROLES,
        "status": InvitationStatus.PENDING,
        "expires_at": EXPIRES_AT,
    }
    values.update(overrides)
    return Invitation(**cast(Any, values))


def test_valid_invitation_stores_all_supplied_values() -> None:
    invitation = _build_invitation()

    assert invitation.id == INVITATION_ID
    assert invitation.tenant_id == TENANT_ID
    assert invitation.email == "manager@example.com"
    assert invitation.roles == MANAGER_ROLES
    assert invitation.status is InvitationStatus.PENDING
    assert invitation.expires_at == EXPIRES_AT


def test_email_is_stripped_and_converted_to_lowercase() -> None:
    invitation = _build_invitation(email="  Manager@Example.COM  ")

    assert invitation.email == "manager@example.com"


def test_empty_email_raises_value_error() -> None:
    with pytest.raises(ValueError, match="email must not be empty"):
        _build_invitation(email="")


def test_whitespace_only_email_raises_value_error() -> None:
    with pytest.raises(ValueError, match="email must not be empty"):
        _build_invitation(email="   \t\n")


def test_non_string_email_raises_type_error() -> None:
    with pytest.raises(TypeError, match="email must be a string"):
        _build_invitation(email=123)


def test_empty_roles_raise_value_error() -> None:
    with pytest.raises(ValueError, match="roles must not be empty"):
        _build_invitation(roles=frozenset())


def test_set_roles_raise_type_error() -> None:
    with pytest.raises(TypeError, match="roles must be a frozenset"):
        _build_invitation(roles={Role.MANAGER})


def test_frozenset_with_string_role_raises_type_error() -> None:
    with pytest.raises(TypeError, match="roles must contain only Role values"):
        _build_invitation(roles=frozenset({"manager"}))


def test_multiple_valid_roles_are_accepted() -> None:
    roles = frozenset({Role.OWNER, Role.MANAGER, Role.ANALYST})
    invitation = _build_invitation(roles=roles)

    assert invitation.roles == roles


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        _build_invitation(id=123)


def test_non_uuid_tenant_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="tenant_id must be a UUID"):
        _build_invitation(tenant_id="00000000-0000-0000-0000-000000000001")


def test_plain_string_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be an InvitationStatus"):
        _build_invitation(status="pending")


def test_another_status_enum_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be an InvitationStatus"):
        _build_invitation(status=MembershipStatus.ACTIVE)


def test_non_datetime_expires_at_raises_type_error() -> None:
    with pytest.raises(TypeError, match="expires_at must be a datetime"):
        _build_invitation(expires_at="2026-12-31T23:59:59Z")


def test_naive_datetime_raises_value_error() -> None:
    with pytest.raises(ValueError, match="expires_at must be timezone-aware"):
        _build_invitation(expires_at=datetime(2026, 12, 31, 23, 59, 59))


def test_timezone_aware_utc_datetime_is_accepted() -> None:
    invitation = _build_invitation(expires_at=EXPIRES_AT)

    assert invitation.expires_at.tzinfo is UTC


@pytest.mark.parametrize(
    "status",
    [
        InvitationStatus.PENDING,
        InvitationStatus.ACCEPTED,
        InvitationStatus.EXPIRED,
        InvitationStatus.REVOKED,
    ],
)
def test_all_invitation_status_values_are_accepted(status: InvitationStatus) -> None:
    invitation = _build_invitation(status=status)

    assert invitation.status is status


def test_invitation_can_be_imported_from_closeros_domain() -> None:
    assert Invitation.__name__ == "Invitation"
