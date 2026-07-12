"""Explicit mapping between tenant ORM rows and domain objects."""

from __future__ import annotations

from uuid import UUID

from closeros.domain.identity import (
    InvitationStatus,
    MembershipStatus,
    Role,
    TenantStatus,
)
from closeros.domain.invitation import Invitation
from closeros.domain.membership import Membership
from closeros.domain.retention import RetentionPolicy
from closeros.domain.tenant import Tenant
from closeros.infrastructure.tenant_orm import (
    InvitationRoleRow,
    InvitationRow,
    MembershipRoleRow,
    MembershipRow,
    TenantRow,
)


def tenant_to_row(tenant: Tenant) -> TenantRow:
    return TenantRow(
        id=tenant.id,
        name=tenant.name,
        status=tenant.status.value,
        time_zone=tenant.time_zone,
        raw_message_days=tenant.retention_policy.raw_message_days,
        sanitized_message_days=tenant.retention_policy.sanitized_message_days,
        ai_output_days=tenant.retention_policy.ai_output_days,
        audit_log_days=tenant.retention_policy.audit_log_days,
        backup_days=tenant.retention_policy.backup_days,
        post_contract_deletion_days=tenant.retention_policy.post_contract_deletion_days,
    )


def tenant_to_domain(row: TenantRow) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        status=TenantStatus(row.status),
        time_zone=row.time_zone,
        retention_policy=RetentionPolicy(
            raw_message_days=row.raw_message_days,
            sanitized_message_days=row.sanitized_message_days,
            ai_output_days=row.ai_output_days,
            audit_log_days=row.audit_log_days,
            backup_days=row.backup_days,
            post_contract_deletion_days=row.post_contract_deletion_days,
        ),
    )


def membership_to_row(membership: Membership) -> MembershipRow:
    return MembershipRow(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        status=membership.status.value,
    )


def membership_role_rows(
    membership_id: UUID,
    roles: frozenset[Role],
) -> tuple[MembershipRoleRow, ...]:
    return tuple(
        MembershipRoleRow(membership_id=membership_id, role=role.value)
        for role in sorted(roles, key=lambda item: item.value)
    )


def membership_to_domain(
    row: MembershipRow,
    roles: frozenset[Role],
) -> Membership:
    return Membership(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        roles=roles,
        status=MembershipStatus(row.status),
    )


def invitation_to_row(invitation: Invitation) -> InvitationRow:
    return InvitationRow(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
    )


def invitation_role_rows(
    invitation_id: UUID,
    roles: frozenset[Role],
) -> tuple[InvitationRoleRow, ...]:
    return tuple(
        InvitationRoleRow(invitation_id=invitation_id, role=role.value)
        for role in sorted(roles, key=lambda item: item.value)
    )


def invitation_to_domain(
    row: InvitationRow,
    roles: frozenset[Role],
) -> Invitation:
    return Invitation(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        roles=roles,
        status=InvitationStatus(row.status),
        expires_at=row.expires_at,
    )
