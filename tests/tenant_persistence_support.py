"""Synthetic fixtures for tenant persistence integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from closeros.domain.identity import InvitationStatus, MembershipStatus, Role, TenantStatus
from closeros.domain.invitation import Invitation
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant

TENANT_A_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_B_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000011")
MEMBERSHIP_A_ID = UUID("00000000-0000-0000-0000-000000000020")
MEMBERSHIP_B_ID = UUID("00000000-0000-0000-0000-000000000021")
INVITATION_A_ID = UUID("00000000-0000-0000-0000-000000000030")
INVITATION_B_ID = UUID("00000000-0000-0000-0000-000000000031")

NOW = datetime(2026, 7, 12, 8, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)

SYNTHETIC_INVITE_EMAIL = "invite.synthetic@example.test"
OTHER_INVITE_EMAIL = "other.invite@example.test"

MANAGER_ROLES = frozenset({Role.MANAGER})
OWNER_ROLES = frozenset({Role.OWNER})
ANALYST_ROLES = frozenset({Role.ANALYST})


def synthetic_retention_policy() -> RetentionPolicy:
    return RetentionPolicy(
        raw_message_days=30,
        sanitized_message_days=30,
        ai_output_days=30,
        audit_log_days=365,
        backup_days=30,
        post_contract_deletion_days=90,
    )


def synthetic_tenant(
    *,
    tenant_id: UUID = TENANT_A_ID,
    name: str = "Synthetic Tenant A",
    status: TenantStatus = TenantStatus.ACTIVE,
    time_zone: str = "Asia/Almaty",
) -> Tenant:
    return Tenant(
        id=tenant_id,
        name=name,
        status=status,
        time_zone=time_zone,
        retention_policy=synthetic_retention_policy(),
    )


def synthetic_membership(
    *,
    membership_id: UUID = MEMBERSHIP_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    user_id: UUID = USER_ID,
    roles: frozenset[Role] = MANAGER_ROLES,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    return Membership(
        id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles,
        status=status,
    )


def synthetic_invitation(
    *,
    invitation_id: UUID = INVITATION_A_ID,
    tenant_id: UUID = TENANT_A_ID,
    email: str = SYNTHETIC_INVITE_EMAIL,
    roles: frozenset[Role] = MANAGER_ROLES,
    status: InvitationStatus = InvitationStatus.PENDING,
    expires_at: datetime = LATER,
) -> Invitation:
    return Invitation(
        id=invitation_id,
        tenant_id=tenant_id,
        email=email,
        roles=roles,
        status=status,
        expires_at=expires_at,
    )
