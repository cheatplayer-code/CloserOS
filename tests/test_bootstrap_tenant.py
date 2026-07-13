"""PostgreSQL integration tests for bootstrap_tenant operator command."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from closeros.application.audit_persistence import AuditAppendRequiredError
from closeros.application.bootstrap_tenant_service import (
    BootstrapEmailNotVerifiedError,
    BootstrapOwnershipConflictError,
    BootstrapTenantResult,
    BootstrapTenantService,
    BootstrapUserInactiveError,
    BootstrapUserNotFoundError,
)
from closeros.domain.authentication import AuthenticationEmail
from closeros.domain.identity import MembershipStatus, Role, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant
from closeros.domain.user import User

from tests.auth_persistence_support import CREDENTIAL_ID, synthetic_credential
from tests.tenant_persistence_support import synthetic_retention_policy, synthetic_tenant

pytestmark = pytest.mark.z0_persistence

OWNER_EMAIL = "bootstrap.owner@example.invalid"
TENANT_NAME = "Synthetic Bootstrap Tenant"
TIME_ZONE = "Asia/Almaty"
OWNER_USER_ID = UUID("00000000-0000-0000-0000-00000000a001")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-00000000a002")


def _service(integrated_uow_factory: Any) -> BootstrapTenantService:
    return BootstrapTenantService(
        uow_factory=integrated_uow_factory,
        uuid_factory=uuid4,
        clock=lambda: synthetic_credential().created_at,
    )


OTHER_CREDENTIAL_ID = UUID("00000000-0000-0000-0000-00000000a012")


async def _seed_verified_owner(
    integrated_uow_factory: Any,
    *,
    email: str = OWNER_EMAIL,
    user_id: UUID = OWNER_USER_ID,
    credential_id: UUID = CREDENTIAL_ID,
    verified: bool = True,
    active: bool = True,
) -> None:
    uow = integrated_uow_factory()
    async with uow:
        await uow.users.add(
            User(
                id=user_id,
                status=UserStatus.ACTIVE if active else UserStatus.DISABLED,
            )
        )
        credential = synthetic_credential(
            credential_id=credential_id,
            user_id=user_id,
            email=AuthenticationEmail(email),
        )
        if verified:
            credential = credential.__class__(
                id=credential.id,
                user_id=credential.user_id,
                email=credential.email,
                password_hash=credential.password_hash,
                created_at=credential.created_at,
                email_verified_at=credential.created_at,
            )
        await uow.credentials.add(credential)
        await uow.commit()


def test_bootstrap_creates_owner_tenant(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        result = await _service(integrated_uow_factory).bootstrap_owner_tenant(
            owner_email=OWNER_EMAIL,
            tenant_name=TENANT_NAME,
            time_zone=TIME_ZONE,
        )
        assert result.status == "created"
        uow = integrated_uow_factory()
        async with uow:
            tenant = await uow.tenants.get_by_id(result.tenant_id)
            memberships = await uow.memberships.list_for_user(OWNER_USER_ID)
        assert tenant is not None
        assert tenant.name == TENANT_NAME
        assert any(Role.OWNER in membership.roles for membership in memberships)

    asyncio.run(exercise())


def test_bootstrap_rolls_back_when_audit_fails(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        service = _service(integrated_uow_factory)
        with (
            patch(
                "closeros.application.bootstrap_tenant_service.append_required_audit_event",
                side_effect=AuditAppendRequiredError("audit failed"),
            ),
            pytest.raises(AuditAppendRequiredError),
        ):
            await service.bootstrap_owner_tenant(
                owner_email=OWNER_EMAIL,
                tenant_name="Audit Failure Tenant",
                time_zone=TIME_ZONE,
            )
        uow = integrated_uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_user(OWNER_USER_ID)
        assert memberships == ()

    asyncio.run(exercise())


def test_bootstrap_rejects_unverified_user(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory, verified=False)
        with pytest.raises(BootstrapEmailNotVerifiedError):
            await _service(integrated_uow_factory).bootstrap_owner_tenant(
                owner_email=OWNER_EMAIL,
                tenant_name=TENANT_NAME,
                time_zone=TIME_ZONE,
            )

    asyncio.run(exercise())


def test_bootstrap_rejects_inactive_user(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory, active=False)
        with pytest.raises(BootstrapUserInactiveError):
            await _service(integrated_uow_factory).bootstrap_owner_tenant(
                owner_email=OWNER_EMAIL,
                tenant_name=TENANT_NAME,
                time_zone=TIME_ZONE,
            )

    asyncio.run(exercise())


def test_bootstrap_rejects_missing_user(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        with pytest.raises(BootstrapUserNotFoundError):
            await _service(integrated_uow_factory).bootstrap_owner_tenant(
                owner_email="missing.owner@example.invalid",
                tenant_name=TENANT_NAME,
                time_zone=TIME_ZONE,
            )

    asyncio.run(exercise())


def test_bootstrap_is_idempotent(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        service = _service(integrated_uow_factory)
        first = await service.bootstrap_owner_tenant(
            owner_email=OWNER_EMAIL,
            tenant_name=TENANT_NAME,
            time_zone=TIME_ZONE,
        )
        second = await service.bootstrap_owner_tenant(
            owner_email=OWNER_EMAIL,
            tenant_name=TENANT_NAME,
            time_zone=TIME_ZONE,
        )
        assert first.tenant_id == second.tenant_id
        assert second.status == "existing"

    asyncio.run(exercise())


def test_bootstrap_handles_concurrent_duplicate_requests(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        service = _service(integrated_uow_factory)

        async def run() -> BootstrapTenantResult:
            return await service.bootstrap_owner_tenant(
                owner_email=OWNER_EMAIL,
                tenant_name="Concurrent Tenant",
                time_zone=TIME_ZONE,
            )

        results = await asyncio.gather(run(), run())
        tenant_ids = {result.tenant_id for result in results}
        assert len(tenant_ids) == 1
        statuses = {result.status for result in results}
        assert statuses.issubset({"created", "existing"})

    asyncio.run(exercise())


def test_bootstrap_rejects_conflicting_non_owner_membership(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        existing_tenant_id = uuid4()
        membership_id = uuid4()
        uow = integrated_uow_factory()
        async with uow:
            await uow.tenants.add(
                Tenant(
                    id=existing_tenant_id,
                    name=TENANT_NAME,
                    status=synthetic_tenant().status,
                    time_zone=TIME_ZONE,
                    retention_policy=synthetic_retention_policy(),
                )
            )
            await uow.memberships.add(
                Membership(
                    id=membership_id,
                    tenant_id=existing_tenant_id,
                    user_id=OWNER_USER_ID,
                    roles=frozenset({Role.MANAGER}),
                    status=MembershipStatus.ACTIVE,
                )
            )
            await uow.commit()
        with pytest.raises(BootstrapOwnershipConflictError):
            await _service(integrated_uow_factory).bootstrap_owner_tenant(
                owner_email=OWNER_EMAIL,
                tenant_name=TENANT_NAME,
                time_zone=TIME_ZONE,
            )

    asyncio.run(exercise())


def test_bootstrap_does_not_leak_across_tenants(integrated_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_verified_owner(integrated_uow_factory)
        await _seed_verified_owner(
            integrated_uow_factory,
            email="other.owner@example.invalid",
            user_id=OTHER_USER_ID,
            credential_id=OTHER_CREDENTIAL_ID,
        )
        service = _service(integrated_uow_factory)
        first = await service.bootstrap_owner_tenant(
            owner_email=OWNER_EMAIL,
            tenant_name="Tenant A",
            time_zone=TIME_ZONE,
        )
        second = await service.bootstrap_owner_tenant(
            owner_email="other.owner@example.invalid",
            tenant_name="Tenant B",
            time_zone=TIME_ZONE,
        )
        assert first.tenant_id != second.tenant_id
        uow = integrated_uow_factory()
        async with uow:
            first_memberships = await uow.memberships.list_for_user(OWNER_USER_ID)
            second_memberships = await uow.memberships.list_for_user(OTHER_USER_ID)
        assert all(membership.tenant_id == first.tenant_id for membership in first_memberships)
        assert all(membership.tenant_id == second.tenant_id for membership in second_memberships)

    asyncio.run(exercise())
