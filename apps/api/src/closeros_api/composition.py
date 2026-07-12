"""API runtime composition and dependency container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from closeros.application.audit_persistence import AuditUnitOfWork
from closeros.application.audit_queries import TenantAuditQueryService
from closeros.application.authentication_persistence import AuthenticationUnitOfWork
from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    MfaRequirementPolicy,
    MfaVerifier,
)
from closeros.application.password_hashing import PasswordHasher
from closeros.application.platform_unit_of_work import PlatformUnitOfWork
from closeros.application.tenant_context import TenantContextResolver, TenantListingService
from closeros.application.tenant_persistence import TenantUnitOfWork
from closeros.infrastructure.audit_unit_of_work import SqlAlchemyAuditUnitOfWork
from closeros.infrastructure.authentication_unit_of_work import SqlAlchemyAuthenticationUnitOfWork
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.infrastructure.platform_unit_of_work import SqlAlchemyPlatformUnitOfWork
from closeros.infrastructure.tenant_unit_of_work import SqlAlchemyTenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from closeros_api.auth_ports import (
    AcceptingMfaVerifier,
    CaptureNotificationDispatcher,
    Clock,
    ConfigurableMfaRequirementPolicy,
    InMemoryRateLimiter,
    NotificationDispatcher,
    RandomUuidFactory,
    RateLimiter,
    SystemClock,
    UuidFactory,
)
from closeros_api.auth_security import SessionCookieConfig, session_cookie_config
from closeros_api.settings import ApiSettings


@dataclass
class ApiRuntimeOverrides:
    workflow_service: AuthenticationWorkflowService | None = None
    uow_factory: Callable[[], AuthenticationUnitOfWork] | None = None
    platform_uow_factory: Callable[[], PlatformUnitOfWork] | None = None
    tenant_uow_factory: Callable[[], TenantUnitOfWork] | None = None
    audit_uow_factory: Callable[[], AuditUnitOfWork] | None = None
    tenant_context_resolver: TenantContextResolver | None = None
    tenant_listing_service: TenantListingService | None = None
    tenant_audit_query_service: TenantAuditQueryService | None = None
    password_hasher: PasswordHasher | None = None
    clock: Clock | None = None
    uuid_factory: UuidFactory | None = None
    mfa_requirement_policy: MfaRequirementPolicy | None = None
    mfa_verifier: MfaVerifier | None = None
    notification_dispatcher: NotificationDispatcher | None = None
    rate_limiter: RateLimiter | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None


AuthRuntimeOverrides = ApiRuntimeOverrides


@dataclass
class ApiRuntime:
    settings: ApiSettings
    workflows: AuthenticationWorkflowService
    password_hasher: PasswordHasher
    clock: Clock
    uuid_factory: UuidFactory
    mfa_requirement_policy: MfaRequirementPolicy
    mfa_verifier: MfaVerifier
    notification_dispatcher: NotificationDispatcher
    rate_limiter: RateLimiter
    cookie_config: SessionCookieConfig
    engine: AsyncEngine | None
    session_factory: async_sessionmaker[AsyncSession] | None
    platform_uow_factory: Callable[[], PlatformUnitOfWork] | None
    tenant_context_resolver: TenantContextResolver
    tenant_listing_service: TenantListingService
    tenant_audit_query_service: TenantAuditQueryService

    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


AuthRuntime = ApiRuntime


class _UnconfiguredTenantContextResolver:
    async def resolve(self, **kwargs: object) -> object:
        raise RuntimeError("tenant context resolver is not configured")


class _UnconfiguredTenantListingService:
    async def list_tenants_for_user(self, **kwargs: object) -> tuple[tuple[object, object], ...]:
        raise RuntimeError("tenant listing service is not configured")


class _UnconfiguredTenantAuditQueryService:
    async def query(self, **kwargs: object) -> object:
        raise RuntimeError("tenant audit query service is not configured")


def build_api_runtime(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None = None,
) -> ApiRuntime:
    override_values = overrides or ApiRuntimeOverrides()
    settings.validate_for_runtime()

    engine = override_values.engine
    session_factory = override_values.session_factory
    if override_values.workflow_service is None and session_factory is None:
        if engine is None:
            engine = create_authentication_engine(normalize_database_url(settings.database_url))
        session_factory = create_authentication_sessionmaker(engine)

    resolved_uow_factory = override_values.uow_factory
    password_hasher = override_values.password_hasher or Argon2idPasswordHasher()
    clock = override_values.clock or SystemClock()
    uuid_factory = override_values.uuid_factory or RandomUuidFactory()

    if settings.is_production:
        if override_values.mfa_requirement_policy is None:
            raise RuntimeError("production MFA requirement policy must be configured explicitly")
        if override_values.notification_dispatcher is None:
            raise RuntimeError("production notification dispatcher must be configured explicitly")
        if override_values.rate_limiter is None:
            raise RuntimeError("production rate limiter must be configured explicitly")
        mfa_policy = override_values.mfa_requirement_policy
        mfa_verifier = override_values.mfa_verifier or AcceptingMfaVerifier()
        dispatcher = override_values.notification_dispatcher
        rate_limiter = override_values.rate_limiter
    else:
        mfa_policy = override_values.mfa_requirement_policy or ConfigurableMfaRequirementPolicy()
        mfa_verifier = override_values.mfa_verifier or AcceptingMfaVerifier()
        dispatcher = override_values.notification_dispatcher or CaptureNotificationDispatcher()
        rate_limiter = override_values.rate_limiter or InMemoryRateLimiter()

    if override_values.workflow_service is None:
        if resolved_uow_factory is None:
            if session_factory is None:
                raise RuntimeError("session factory is required to build the unit of work")

            def resolved_uow_factory() -> AuthenticationUnitOfWork:
                return cast(
                    AuthenticationUnitOfWork,
                    SqlAlchemyAuthenticationUnitOfWork(session_factory),
                )

        workflows = AuthenticationWorkflowService(
            uow_factory=resolved_uow_factory,
            password_hasher=password_hasher,
            session_touch_interval=settings.session_touch_interval,
        )
    else:
        workflows = override_values.workflow_service

    platform_uow_factory = override_values.platform_uow_factory
    tenant_uow_factory = override_values.tenant_uow_factory
    audit_uow_factory = override_values.audit_uow_factory

    if session_factory is not None:
        if platform_uow_factory is None:

            def platform_uow_factory() -> PlatformUnitOfWork:
                return cast(
                    PlatformUnitOfWork,
                    SqlAlchemyPlatformUnitOfWork(session_factory),
                )

        if tenant_uow_factory is None:

            def tenant_uow_factory() -> TenantUnitOfWork:
                return cast(
                    TenantUnitOfWork,
                    SqlAlchemyTenantUnitOfWork(session_factory),
                )

        if audit_uow_factory is None:

            def audit_uow_factory() -> AuditUnitOfWork:
                return cast(
                    AuditUnitOfWork,
                    SqlAlchemyAuditUnitOfWork(session_factory),
                )

    tenant_context_resolver = override_values.tenant_context_resolver
    if tenant_context_resolver is None:
        if platform_uow_factory is not None:
            tenant_context_resolver = TenantContextResolver(
                uow_factory=platform_uow_factory,
                session_touch_interval=settings.session_touch_interval,
            )
        else:
            tenant_context_resolver = cast(
                TenantContextResolver,
                _UnconfiguredTenantContextResolver(),
            )

    tenant_listing_service = override_values.tenant_listing_service
    if tenant_listing_service is None:
        if tenant_uow_factory is not None:
            tenant_listing_service = TenantListingService(uow_factory=tenant_uow_factory)
        else:
            tenant_listing_service = cast(
                TenantListingService,
                _UnconfiguredTenantListingService(),
            )

    tenant_audit_query_service = override_values.tenant_audit_query_service
    if tenant_audit_query_service is None:
        if audit_uow_factory is not None:
            tenant_audit_query_service = TenantAuditQueryService(
                audit_uow_factory=audit_uow_factory,
            )
        else:
            tenant_audit_query_service = cast(
                TenantAuditQueryService,
                _UnconfiguredTenantAuditQueryService(),
            )

    return ApiRuntime(
        settings=settings,
        workflows=workflows,
        password_hasher=password_hasher,
        clock=clock,
        uuid_factory=uuid_factory,
        mfa_requirement_policy=mfa_policy,
        mfa_verifier=mfa_verifier,
        notification_dispatcher=dispatcher,
        rate_limiter=rate_limiter,
        cookie_config=session_cookie_config(is_production=settings.is_production),
        engine=engine,
        session_factory=session_factory,
        platform_uow_factory=platform_uow_factory,
        tenant_context_resolver=tenant_context_resolver,
        tenant_listing_service=tenant_listing_service,
        tenant_audit_query_service=tenant_audit_query_service,
    )


def build_auth_runtime(
    settings: ApiSettings,
    overrides: ApiRuntimeOverrides | None = None,
) -> ApiRuntime:
    return build_api_runtime(settings, overrides)
