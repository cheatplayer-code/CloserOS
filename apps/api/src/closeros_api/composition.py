"""Authentication API runtime composition and dependency container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from closeros.application.authentication_persistence import AuthenticationUnitOfWork
from closeros.application.authentication_workflows import (
    AuthenticationWorkflowService,
    MfaRequirementPolicy,
    MfaVerifier,
)
from closeros.application.password_hashing import PasswordHasher
from closeros.infrastructure.authentication_unit_of_work import SqlAlchemyAuthenticationUnitOfWork
from closeros.infrastructure.database import (
    create_authentication_engine,
    create_authentication_sessionmaker,
    normalize_database_url,
)
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
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
class AuthRuntimeOverrides:
    workflow_service: AuthenticationWorkflowService | None = None
    uow_factory: Callable[[], AuthenticationUnitOfWork] | None = None
    password_hasher: PasswordHasher | None = None
    clock: Clock | None = None
    uuid_factory: UuidFactory | None = None
    mfa_requirement_policy: MfaRequirementPolicy | None = None
    mfa_verifier: MfaVerifier | None = None
    notification_dispatcher: NotificationDispatcher | None = None
    rate_limiter: RateLimiter | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None


@dataclass
class AuthRuntime:
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

    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


def build_auth_runtime(
    settings: ApiSettings,
    overrides: AuthRuntimeOverrides | None = None,
) -> AuthRuntime:
    override_values = overrides or AuthRuntimeOverrides()
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

    return AuthRuntime(
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
    )
