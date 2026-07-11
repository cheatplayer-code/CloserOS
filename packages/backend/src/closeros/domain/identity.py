"""Framework-independent identity enums for tenant and user domain."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    SALES_HEAD = "sales_head"
    MANAGER = "manager"
    ANALYST = "analyst"
    COMPLIANCE_ADMIN = "compliance_admin"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"
