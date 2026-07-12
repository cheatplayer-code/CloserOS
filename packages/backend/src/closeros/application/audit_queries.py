"""Tenant-scoped authorized audit query service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from closeros.application.audit_persistence import (
    AuditQueryCursor,
    AuditQueryFilter,
    AuditQueryPage,
    AuditUnitOfWork,
)
from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.domain.access import (
    TENANT_ACCESS_DENIED_MESSAGE,
    TenantAccessDeniedError,
    require_tenant_access,
)
from closeros.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditScope,
    AuditTargetType,
    MetadataScalar,
    build_audit_event,
)
from closeros.domain.identity import Role
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant
from closeros.domain.user import User

_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 50
_PRIVILEGED_AUDIT_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.COMPLIANCE_ADMIN})
_AuditUnitOfWorkFactory = Callable[[], AuditUnitOfWork]


class TenantAuditQueryDeniedError(PermissionError):
    """Raised when tenant audit query authorization fails."""

    def __init__(self, message: str = TENANT_ACCESS_DENIED_MESSAGE) -> None:
        super().__init__(message)


@dataclass
class TenantAuditQueryService:
    audit_uow_factory: _AuditUnitOfWorkFactory

    def _require_privileged_access(
        self,
        *,
        tenant: Tenant,
        user: User,
        membership: Membership,
    ) -> None:
        try:
            require_tenant_access(tenant=tenant, user=user, membership=membership)
        except TenantAccessDeniedError as error:
            raise TenantAuditQueryDeniedError(TENANT_ACCESS_DENIED_MESSAGE) from error

        if not _PRIVILEGED_AUDIT_ROLES.intersection(membership.roles):
            raise TenantAuditQueryDeniedError(TENANT_ACCESS_DENIED_MESSAGE)

    async def query(
        self,
        *,
        tenant: Tenant,
        user: User,
        membership: Membership,
        query_filter: AuditQueryFilter,
        audit_context: AuditContext,
        occurred_at: datetime,
        cursor: AuditQueryCursor | None = None,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> AuditQueryPage:
        self._require_privileged_access(tenant=tenant, user=user, membership=membership)

        if query_filter.tenant_id != tenant.id:
            raise TenantAuditQueryDeniedError(TENANT_ACCESS_DENIED_MESSAGE)

        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError("page_size must be a positive integer")

        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")

        bounded_page_size = min(page_size, _MAX_PAGE_SIZE)
        uow = self.audit_uow_factory()
        async with uow:
            page = await uow.audit_events.query_page(
                query_filter=query_filter,
                cursor=cursor,
                page_size=bounded_page_size,
            )
            viewed_event = build_audit_event(
                event_id=uuid4(),
                scope=AuditScope.TENANT,
                tenant_id=tenant.id,
                actor_type=AuditActorType.USER,
                actor_id=user.id,
                action=AuditAction.AUDIT_LOG_VIEWED,
                target_type=AuditTargetType.AUDIT_LOG,
                target_id=tenant.id,
                occurred_at=occurred_at,
                correlation_id=audit_context.correlation_id,
                metadata=_audit_view_metadata(audit_context),
            )
            await append_required_audit_event(uow.audit_events, viewed_event)
            await uow.commit()

        return page


def _audit_view_metadata(audit_context: AuditContext) -> dict[str, MetadataScalar]:
    metadata: dict[str, MetadataScalar] = {"outcome": "success"}
    if audit_context.http_method is not None:
        metadata["http_method"] = audit_context.http_method
    if audit_context.route_template is not None:
        metadata["route_template"] = audit_context.route_template
    return metadata
