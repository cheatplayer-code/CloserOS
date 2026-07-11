"""Tests for CLS-010.2b user domain entity."""

from uuid import UUID

import pytest
from closeros.domain import User
from closeros.domain.identity import TenantStatus, UserStatus

USER_ID = UUID("00000000-0000-0000-0000-000000000010")


def test_valid_user_with_active_status() -> None:
    user = User(id=USER_ID, status=UserStatus.ACTIVE)

    assert user.id == USER_ID
    assert user.status is UserStatus.ACTIVE


def test_disabled_status_is_accepted() -> None:
    user = User(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        status=UserStatus.DISABLED,
    )

    assert user.status is UserStatus.DISABLED


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        User(id=123, status=UserStatus.ACTIVE)  # type: ignore[arg-type]


def test_string_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        User(
            id="00000000-0000-0000-0000-000000000010",  # type: ignore[arg-type]
            status=UserStatus.ACTIVE,
        )


def test_string_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be a UserStatus"):
        User(id=USER_ID, status="active")  # type: ignore[arg-type]


def test_tenant_status_used_as_user_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be a UserStatus"):
        User(id=USER_ID, status=TenantStatus.ACTIVE)  # type: ignore[arg-type]


def test_user_can_be_imported_from_closeros_domain() -> None:
    assert User.__name__ == "User"
