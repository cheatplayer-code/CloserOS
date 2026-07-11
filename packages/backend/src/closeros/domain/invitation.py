"""Framework-independent invitation domain entity."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from closeros.domain.identity import InvitationStatus, Role


@dataclass(slots=True)
class Invitation:
    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[Role]
    status: InvitationStatus
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")

        if not isinstance(self.email, str):
            raise TypeError("email must be a string")

        normalized_email = self.email.strip().lower()

        if not normalized_email:
            raise ValueError("email must not be empty")

        if not isinstance(self.roles, frozenset):
            raise TypeError("roles must be a frozenset")

        if not self.roles:
            raise ValueError("roles must not be empty")

        if any(not isinstance(role, Role) for role in self.roles):
            raise TypeError("roles must contain only Role values")

        if not isinstance(self.status, InvitationStatus):
            raise TypeError("status must be an InvitationStatus")

        if not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime")

        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")

        self.email = normalized_email
