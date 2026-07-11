"""Tests for CLS-010.2a tenant domain entity."""

from uuid import UUID

import pytest
from closeros.domain import Tenant
from closeros.domain.identity import TenantStatus

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_valid_tenant_stores_uuid_normalized_name_and_status() -> None:
    tenant = Tenant(
        id=TENANT_ID,
        name="  Acme Corp  ",
        status=TenantStatus.ACTIVE,
    )

    assert tenant.id == TENANT_ID
    assert tenant.name == "Acme Corp"
    assert tenant.status is TenantStatus.ACTIVE


def test_surrounding_whitespace_is_stripped() -> None:
    tenant = Tenant(
        id=TENANT_ID,
        name="\t  Example Tenant  \n",
        status=TenantStatus.SUSPENDED,
    )

    assert tenant.name == "Example Tenant"


def test_empty_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        Tenant(id=TENANT_ID, name="", status=TenantStatus.ACTIVE)


def test_whitespace_only_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        Tenant(id=TENANT_ID, name="   \t\n", status=TenantStatus.ACTIVE)


def test_non_string_name_raises_type_error() -> None:
    with pytest.raises(TypeError, match="name must be a string"):
        Tenant(id=TENANT_ID, name=123, status=TenantStatus.ACTIVE)  # type: ignore[arg-type]


def test_non_uuid_id_raises_type_error() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        Tenant(
            id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
            name="Acme Corp",
            status=TenantStatus.ACTIVE,
        )


def test_plain_string_status_raises_type_error() -> None:
    with pytest.raises(TypeError, match="status must be a TenantStatus"):
        Tenant(id=TENANT_ID, name="Acme Corp", status="active")  # type: ignore[arg-type]


def test_active_and_suspended_statuses_are_accepted() -> None:
    active_tenant = Tenant(
        id=TENANT_ID,
        name="Active Tenant",
        status=TenantStatus.ACTIVE,
    )
    suspended_tenant = Tenant(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Suspended Tenant",
        status=TenantStatus.SUSPENDED,
    )

    assert active_tenant.status is TenantStatus.ACTIVE
    assert suspended_tenant.status is TenantStatus.SUSPENDED


def test_tenant_can_be_imported_from_closeros_domain() -> None:
    assert Tenant.__name__ == "Tenant"
