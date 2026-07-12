"""Tenant context resolution and tenant listing services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn
from uuid import UUID

from closeros.application.authentication_workflows import AUTHENTICATION_UNAVAILABLE_MESSAGE
from closeros.application.platform_unit_of_work import PlatformUnitOfWork
from closeros.application.tenant_persistence import TenantUnitOfWork
from closeros.domain.access import (
    TENANT_ACCESS_DENIED_MESSAGE,
    TenantAccessDeniedError,
    require_tenant_access,
)
from closeros.domain.authentication import AuthenticationSessionStage
from closeros.domain.authentication_policy import (
    AuthenticationSessionUnavailableError,
    require_usable_authentication_session,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_timeout import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionTimeoutPolicy,
)
from closeros.domain.identity import MembershipStatus, TenantStatus, UserStatus
from closeros.domain.membership import Membership
from closeros.domain.tenant import Tenant
from closeros.domain.user import User
from closeros.security.authentication_tokens import (
    RawAuthenticationToken,
    hash_authentication_token,
)

_UnitOfWorkFactory = Callable[[], PlatformUnitOfWork]
_DEFAULT_SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


class TenantContextUnavailableError(Exception):
    """Raised when the authentication session is missing or unusable."""

    def __init__(self, message: str = AUTHENTICATION_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant: Tenant
    user: User
    membership: Membership
    correlation_id: UUID


def _validate_timezone_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    return value


def _raise_access_denied() -> NoReturn:
    raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)


def _raise_unavailable() -> NoReturn:
    raise TenantContextUnavailableError(AUTHENTICATION_UNAVAILABLE_MESSAGE)


class TenantContextResolver:
    """Resolve tenant-scoped request context from a session token and tenant ID."""

    def __init__(
        self,
        *,
        uow_factory: _UnitOfWorkFactory,
        session_timeout_policy: AuthenticationSessionTimeoutPolicy = (
            AUTHENTICATION_SESSION_TIMEOUT_POLICY
        ),
        session_touch_interval: timedelta = _DEFAULT_SESSION_TOUCH_INTERVAL,
    ) -> None:
        self._uow_factory = uow_factory
        self._session_timeout_policy = session_timeout_policy
        self._session_touch_interval = session_touch_interval

    async def resolve(
        self,
        *,
        raw_token: RawAuthenticationToken,
        tenant_id: UUID,
        correlation_id: UUID,
        now: datetime,
        touch_session: bool = True,
    ) -> TenantContext:
        if not isinstance(raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")

        if not isinstance(correlation_id, UUID):
            raise TypeError("correlation_id must be a UUID")

        validated_now = _validate_timezone_aware_datetime(now, "now")
        token_hash = hash_authentication_token(raw_token)

        uow = self._uow_factory()
        async with uow:
            session = await uow.sessions.get_by_token_hash(token_hash)
            if session is None:
                _raise_unavailable()

            if session.stage is not AuthenticationSessionStage.AUTHENTICATED:
                _raise_unavailable()

            try:
                require_usable_authentication_session(
                    session=session,
                    now=validated_now,
                    policy=self._session_timeout_policy,
                )
            except AuthenticationSessionUnavailableError as error:
                raise TenantContextUnavailableError(AUTHENTICATION_UNAVAILABLE_MESSAGE) from error

            user = await uow.users.get_by_id(session.user_id)
            if user is None or user.status is not UserStatus.ACTIVE:
                _raise_unavailable()

            tenant = await uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                _raise_access_denied()

            membership = await uow.memberships.get_by_tenant_and_user(
                tenant_id,
                user.id,
            )
            if membership is None:
                _raise_access_denied()

            try:
                require_tenant_access(
                    tenant=tenant,
                    user=user,
                    membership=membership,
                )
            except TenantAccessDeniedError as error:
                raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE) from error

            if touch_session and (
                validated_now - session.last_seen_at >= self._session_touch_interval
            ):
                await uow.sessions.update_last_seen(
                    session_id=session.id,
                    last_seen_at=validated_now,
                )
                session = AuthenticationSession(
                    id=session.id,
                    user_id=session.user_id,
                    token_hash=session.token_hash,
                    stage=session.stage,
                    assurance_level=session.assurance_level,
                    mfa_completed=session.mfa_completed,
                    created_at=session.created_at,
                    last_seen_at=validated_now,
                    expires_at=session.expires_at,
                    revoked_at=session.revoked_at,
                )
                await uow.commit()
            else:
                await uow.rollback()

        return TenantContext(
            tenant=tenant,
            user=user,
            membership=membership,
            correlation_id=correlation_id,
        )


class TenantListingService:
    """List tenants accessible to a user through active memberships."""

    def __init__(self, *, uow_factory: Callable[[], TenantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def list_tenants_for_user(
        self,
        *,
        user_id: UUID,
    ) -> tuple[tuple[Tenant, Membership], ...]:
        if not isinstance(user_id, UUID):
            raise TypeError("user_id must be a UUID")

        uow = self._uow_factory()
        async with uow:
            memberships = await uow.memberships.list_for_user(user_id)
            accessible: list[tuple[Tenant, Membership]] = []
            for membership in memberships:
                if membership.status is not MembershipStatus.ACTIVE:
                    continue

                tenant = await uow.tenants.get_by_id(membership.tenant_id)
                if tenant is None or tenant.status is not TenantStatus.ACTIVE:
                    continue

                accessible.append((tenant, membership))

            await uow.rollback()

        return tuple(sorted(accessible, key=lambda item: (item[0].name, item[0].id)))
