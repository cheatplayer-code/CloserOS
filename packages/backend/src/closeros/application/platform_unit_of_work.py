"""Application-layer unit-of-work port composing authentication and tenancy."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from closeros.application.audit_persistence import AuditEventAppendRepository
from closeros.application.authentication_persistence import (
    CredentialRepository,
    OneTimeTokenRepository,
    SessionRepository,
    UserRepository,
)
from closeros.application.tenant_persistence import (
    InvitationRepository,
    MembershipRepository,
    TenantRepository,
)


class PlatformUnitOfWork(Protocol):
    users: UserRepository
    credentials: CredentialRepository
    sessions: SessionRepository
    one_time_tokens: OneTimeTokenRepository
    tenants: TenantRepository
    memberships: MembershipRepository
    invitations: InvitationRepository
    audit_events: AuditEventAppendRepository

    async def __aenter__(self) -> PlatformUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
