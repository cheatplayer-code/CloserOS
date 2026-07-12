"""Authorization tests for tenant-scoped audit queries."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from closeros.application.audit_persistence import AuditQueryFilter
from closeros.application.audit_queries import TenantAuditQueryDeniedError, TenantAuditQueryService
from closeros.application.audit_recording import AuditContext
from closeros.domain.identity import MembershipStatus, Role, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.domain.user import User

from tests.test_audit_support import tenant_event

pytestmark = pytest.mark.auth_persistence

TENANT_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000020")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000030")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000021")
NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
AUDIT_CONTEXT = AuditContext(correlation_id=UUID("00000000-0000-0000-0000-000000000999"))


def _tenant(*, status: TenantStatus = TenantStatus.ACTIVE) -> Tenant:
    return Tenant(
        id=TENANT_ID,
        name="Synthetic Tenant",
        status=status,
        time_zone="UTC",
        retention_policy=RetentionPolicy(
            raw_message_days=365,
            sanitized_message_days=365,
            ai_output_days=365,
            audit_log_days=365,
            backup_days=365,
            post_contract_deletion_days=365,
        ),
    )


def _user(*, status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(id=USER_ID, status=status)


def _membership(
    *, roles: frozenset[Role], status: MembershipStatus = MembershipStatus.ACTIVE
) -> Membership:
    return Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        roles=roles,
        status=status,
    )


async def _seed_event(auth_audit_uow_factory: Any) -> None:
    uow = auth_audit_uow_factory()
    async with uow:
        await uow.audit_events.append(tenant_event(tenant_id=TENANT_ID))
        await uow.commit()


def test_owner_can_query_and_records_audit_log_viewed(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_event(auth_audit_uow_factory)
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        page = await service.query(
            tenant=_tenant(),
            user=_user(),
            membership=_membership(roles=frozenset({Role.OWNER})),
            query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
            audit_context=AUDIT_CONTEXT,
            occurred_at=NOW,
        )
        assert len(page.events) >= 1
        uow = auth_audit_uow_factory()
        async with uow:
            viewed = await uow.audit_events.query_page(
                query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
                cursor=None,
                page_size=10,
            )
        assert any(event.action.value == "audit.log_viewed" for event in viewed.events)

    asyncio.run(exercise())


def test_compliance_admin_can_query(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        await _seed_event(auth_audit_uow_factory)
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        page = await service.query(
            tenant=_tenant(),
            user=_user(),
            membership=_membership(roles=frozenset({Role.COMPLIANCE_ADMIN})),
            query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
            audit_context=AUDIT_CONTEXT,
            occurred_at=NOW,
        )
        assert len(page.events) >= 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "roles",
    [
        frozenset({Role.MANAGER}),
        frozenset({Role.ANALYST}),
        frozenset({Role.SALES_HEAD}),
    ],
)
def test_non_privileged_roles_are_denied(
    auth_audit_uow_factory: Any, roles: frozenset[Role]
) -> None:
    async def exercise() -> None:
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        with pytest.raises(TenantAuditQueryDeniedError, match="tenant access denied"):
            await service.query(
                tenant=_tenant(),
                user=_user(),
                membership=_membership(roles=roles),
                query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
                audit_context=AUDIT_CONTEXT,
                occurred_at=NOW,
            )

    asyncio.run(exercise())


def test_suspended_tenant_is_denied(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        with pytest.raises(TenantAuditQueryDeniedError, match="tenant access denied"):
            await service.query(
                tenant=_tenant(status=TenantStatus.SUSPENDED),
                user=_user(),
                membership=_membership(roles=frozenset({Role.OWNER})),
                query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
                audit_context=AUDIT_CONTEXT,
                occurred_at=NOW,
            )

    asyncio.run(exercise())


def test_mismatched_membership_is_denied(auth_audit_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        membership = Membership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            user_id=OTHER_USER_ID,
            roles=frozenset({Role.OWNER}),
            status=MembershipStatus.ACTIVE,
        )
        with pytest.raises(TenantAuditQueryDeniedError, match="tenant access denied"):
            await service.query(
                tenant=_tenant(),
                user=_user(),
                membership=membership,
                query_filter=AuditQueryFilter(tenant_id=TENANT_ID),
                audit_context=AUDIT_CONTEXT,
                occurred_at=NOW,
            )

    asyncio.run(exercise())


def test_cross_tenant_filter_is_denied(auth_audit_uow_factory: Any) -> None:
    other_tenant = UUID("00000000-0000-0000-0000-000000000099")

    async def exercise() -> None:
        service = TenantAuditQueryService(audit_uow_factory=auth_audit_uow_factory)
        with pytest.raises(TenantAuditQueryDeniedError, match="tenant access denied"):
            await service.query(
                tenant=_tenant(),
                user=_user(),
                membership=_membership(roles=frozenset({Role.OWNER})),
                query_filter=AuditQueryFilter(tenant_id=other_tenant),
                audit_context=AUDIT_CONTEXT,
                occurred_at=NOW,
            )

    asyncio.run(exercise())
