"""Framework-independent authentication workflows backed by persistence.

Every multi-step workflow opens one unit-of-work transaction, performs all
repository operations, and commits exactly once. Repositories never commit
independently. All timestamps and identifiers are supplied by callers or
injected factories; workflows never read the system clock.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NoReturn, Protocol
from uuid import UUID

from closeros.application.authentication_issuance import (
    AuthenticationSessionTransitionError,
    IssuedAuthenticationSession,
    complete_pending_mfa_and_rotate_session,
    issue_authenticated_session,
    issue_authentication_one_time_token,
    issue_pending_mfa_session,
)
from closeros.application.authentication_persistence import (
    AuthenticationUnitOfWork,
    DuplicateCredentialEmailError,
    DuplicateUserCredentialError,
)
from closeros.application.password_hashing import PasswordHasher
from closeros.domain.authentication import (
    AuthenticationAssuranceLevel,
    AuthenticationEmail,
    AuthenticationSessionStage,
    AuthenticationTokenPurpose,
    MfaMethod,
)
from closeros.domain.authentication_policy import (
    AuthenticationSessionUnavailableError,
    AuthenticationTokenUnavailableError,
    require_usable_authentication_session,
    require_usable_authentication_token,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_timeout import (
    AUTHENTICATION_SESSION_TIMEOUT_POLICY,
    AuthenticationSessionTimeoutPolicy,
)
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import UserStatus
from closeros.domain.user import User
from closeros.security.authentication_tokens import (
    RawAuthenticationToken,
    generate_raw_authentication_token,
    hash_authentication_token,
)

_RawAuthenticationTokenFactory = Callable[[], RawAuthenticationToken]
_UnitOfWorkFactory = Callable[[], AuthenticationUnitOfWork]

AUTHENTICATION_FAILED_MESSAGE = "authentication failed"
AUTHENTICATION_UNAVAILABLE_MESSAGE = "authentication unavailable"
REGISTRATION_UNAVAILABLE_MESSAGE = "registration unavailable"
AUTHENTICATION_REQUEST_ACCEPTED_MESSAGE = "authentication request accepted"


class AuthenticationFailedError(Exception):
    """Raised when password authentication fails."""

    def __init__(self, message: str = AUTHENTICATION_FAILED_MESSAGE) -> None:
        super().__init__(message)


class AuthenticationWorkflowUnavailableError(Exception):
    """Raised when an authentication workflow or token cannot be used."""

    def __init__(self, message: str = AUTHENTICATION_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message)


class RegistrationUnavailableError(Exception):
    """Raised when registration cannot complete."""

    def __init__(self, message: str = REGISTRATION_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AuthenticationNotificationDelivery:
    """Internal email-delivery payload hidden from public repr."""

    recipient: AuthenticationEmail = field(repr=False)
    raw_token: RawAuthenticationToken = field(repr=False)


@dataclass(frozen=True, slots=True)
class AuthenticationRequestAccepted:
    """Generic accepted result for verification or reset requests."""

    message: str = AUTHENTICATION_REQUEST_ACCEPTED_MESSAGE
    delivery: AuthenticationNotificationDelivery | None = None


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user_id: UUID
    delivery: AuthenticationNotificationDelivery


@dataclass(frozen=True, slots=True)
class ResolvedAuthenticationSession:
    session: AuthenticationSession
    user: User


class MfaVerifier(Protocol):
    """Port for verifying MFA responses without exposing authenticator secrets."""

    async def verify_mfa(
        self,
        *,
        user_id: UUID,
        method: MfaMethod,
        response: object,
    ) -> bool: ...


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _normalize_email(value: str) -> AuthenticationEmail:
    if not isinstance(value, str):
        raise TypeError("email must be a string")
    return AuthenticationEmail(value=value)


def _raise_login_failed() -> NoReturn:
    raise AuthenticationFailedError(AUTHENTICATION_FAILED_MESSAGE)


def _raise_unavailable() -> NoReturn:
    raise AuthenticationWorkflowUnavailableError(AUTHENTICATION_UNAVAILABLE_MESSAGE)


async def _load_active_user(
    uow: AuthenticationUnitOfWork,
    *,
    user_id: UUID,
) -> User | None:
    user = await uow.users.get_by_id(user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        return None
    return user


async def _verify_password_or_fail(
    password_hasher: PasswordHasher,
    *,
    candidate: str,
    stored: EmailPasswordCredential,
) -> bool:
    if not isinstance(candidate, str):
        raise TypeError("password must be a string")

    verification = password_hasher.verify_password(
        candidate=candidate,
        stored=stored.password_hash,
    )
    if not verification.is_valid:
        _raise_login_failed()

    return verification.requires_rehash


async def _issue_verification_delivery(
    uow: AuthenticationUnitOfWork,
    *,
    user_id: UUID,
    credential: EmailPasswordCredential,
    verification_token_id: UUID,
    issued_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory,
) -> AuthenticationNotificationDelivery:
    await uow.one_time_tokens.revoke_active_for_user_and_purpose(
        user_id=user_id,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        revoked_at=issued_at,
    )
    issued = issue_authentication_one_time_token(
        token_id=verification_token_id,
        user_id=user_id,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=issued_at,
        raw_token_factory=raw_token_factory,
    )
    await uow.one_time_tokens.add(issued.token)
    return AuthenticationNotificationDelivery(
        recipient=credential.email,
        raw_token=issued.raw_token,
    )


async def _issue_reset_delivery(
    uow: AuthenticationUnitOfWork,
    *,
    user_id: UUID,
    credential: EmailPasswordCredential,
    reset_token_id: UUID,
    requested_at: datetime,
    raw_token_factory: _RawAuthenticationTokenFactory,
) -> AuthenticationNotificationDelivery:
    await uow.one_time_tokens.revoke_active_for_user_and_purpose(
        user_id=user_id,
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        revoked_at=requested_at,
    )
    issued = issue_authentication_one_time_token(
        token_id=reset_token_id,
        user_id=user_id,
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        issued_at=requested_at,
        raw_token_factory=raw_token_factory,
    )
    await uow.one_time_tokens.add(issued.token)
    return AuthenticationNotificationDelivery(
        recipient=credential.email,
        raw_token=issued.raw_token,
    )


def _eligible_for_verification_delivery(
    user: User | None,
    credential: EmailPasswordCredential | None,
) -> bool:
    return (
        user is not None
        and user.status is UserStatus.ACTIVE
        and credential is not None
        and credential.email_verified_at is None
    )


def _eligible_for_reset_delivery(
    user: User | None,
    credential: EmailPasswordCredential | None,
) -> bool:
    return (
        user is not None
        and user.status is UserStatus.ACTIVE
        and credential is not None
        and credential.email_verified_at is not None
    )


async def _consume_locked_one_time_token(
    uow: AuthenticationUnitOfWork,
    *,
    token: AuthenticationOneTimeToken,
    consumed_at: datetime,
    expected_purpose: AuthenticationTokenPurpose,
) -> None:
    if token.purpose is not expected_purpose:
        _raise_unavailable()

    try:
        require_usable_authentication_token(token=token, now=consumed_at)
    except AuthenticationTokenUnavailableError as error:
        raise AuthenticationWorkflowUnavailableError(AUTHENTICATION_UNAVAILABLE_MESSAGE) from error

    consumed = await uow.one_time_tokens.consume_if_usable(
        token_id=token.id,
        consumed_at=consumed_at,
        now=consumed_at,
    )
    if not consumed:
        _raise_unavailable()


@dataclass
class AuthenticationWorkflowService:
    """Orchestrates authentication workflows through a unit-of-work factory."""

    uow_factory: _UnitOfWorkFactory
    password_hasher: PasswordHasher
    session_touch_interval: timedelta = timedelta(minutes=5)
    session_timeout_policy: AuthenticationSessionTimeoutPolicy = (
        AUTHENTICATION_SESSION_TIMEOUT_POLICY
    )

    async def register_user(
        self,
        *,
        user_id: UUID,
        credential_id: UUID,
        verification_token_id: UUID,
        email: str,
        plaintext_password: str,
        registered_at: datetime,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> RegistrationResult:
        validated_user_id = _validate_uuid(user_id, "user_id")
        validated_credential_id = _validate_uuid(credential_id, "credential_id")
        validated_token_id = _validate_uuid(
            verification_token_id,
            "verification_token_id",
        )
        validated_registered_at = _validate_timezone_aware_datetime(
            registered_at,
            "registered_at",
        )
        normalized_email = _normalize_email(email)
        password_hash = self.password_hasher.hash_password(plaintext_password)
        credential = EmailPasswordCredential(
            id=validated_credential_id,
            user_id=validated_user_id,
            email=normalized_email,
            password_hash=password_hash,
            created_at=validated_registered_at,
            email_verified_at=None,
        )

        uow = self.uow_factory()
        async with uow:
            try:
                await uow.users.add(User(id=validated_user_id, status=UserStatus.ACTIVE))
                await uow.credentials.add(credential)
            except (
                DuplicateCredentialEmailError,
                DuplicateUserCredentialError,
            ) as error:
                raise RegistrationUnavailableError(REGISTRATION_UNAVAILABLE_MESSAGE) from error

            delivery = await _issue_verification_delivery(
                uow,
                user_id=validated_user_id,
                credential=credential,
                verification_token_id=validated_token_id,
                issued_at=validated_registered_at,
                raw_token_factory=raw_token_factory,
            )
            await uow.commit()

        return RegistrationResult(user_id=validated_user_id, delivery=delivery)

    async def request_email_verification(
        self,
        *,
        email: str,
        verification_token_id: UUID,
        requested_at: datetime,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> AuthenticationRequestAccepted:
        validated_token_id = _validate_uuid(
            verification_token_id,
            "verification_token_id",
        )
        validated_requested_at = _validate_timezone_aware_datetime(
            requested_at,
            "requested_at",
        )
        normalized_email = _normalize_email(email)

        uow = self.uow_factory()
        async with uow:
            credential = await uow.credentials.get_by_email(normalized_email)
            user = (
                await _load_active_user(uow, user_id=credential.user_id)
                if credential is not None
                else None
            )
            delivery: AuthenticationNotificationDelivery | None = None
            if _eligible_for_verification_delivery(user, credential):
                assert credential is not None
                delivery = await _issue_verification_delivery(
                    uow,
                    user_id=credential.user_id,
                    credential=credential,
                    verification_token_id=validated_token_id,
                    issued_at=validated_requested_at,
                    raw_token_factory=raw_token_factory,
                )
            await uow.commit()

        return AuthenticationRequestAccepted(delivery=delivery)

    async def confirm_email_verification(
        self,
        *,
        raw_token: RawAuthenticationToken,
        confirmed_at: datetime,
    ) -> None:
        if not isinstance(raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")

        validated_confirmed_at = _validate_timezone_aware_datetime(
            confirmed_at,
            "confirmed_at",
        )
        token_hash = hash_authentication_token(raw_token)

        uow = self.uow_factory()
        async with uow:
            token = await uow.one_time_tokens.get_by_token_hash_for_update(token_hash)
            if token is None:
                _raise_unavailable()

            await _consume_locked_one_time_token(
                uow,
                token=token,
                consumed_at=validated_confirmed_at,
                expected_purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
            )

            credential = await uow.credentials.get_by_user_id(token.user_id)
            if credential is None:
                _raise_unavailable()

            await uow.credentials.set_email_verified_at(
                credential_id=credential.id,
                verified_at=validated_confirmed_at,
            )
            await uow.one_time_tokens.revoke_active_for_user_and_purpose(
                user_id=token.user_id,
                purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
                revoked_at=validated_confirmed_at,
            )
            await uow.commit()

    async def login_with_password(
        self,
        *,
        email: str,
        plaintext_password: str,
        session_id: UUID,
        authenticated_at: datetime,
        mfa_required: bool,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> IssuedAuthenticationSession:
        validated_session_id = _validate_uuid(session_id, "session_id")
        validated_authenticated_at = _validate_timezone_aware_datetime(
            authenticated_at,
            "authenticated_at",
        )
        normalized_email = _normalize_email(email)

        uow = self.uow_factory()
        async with uow:
            credential = await uow.credentials.get_by_email_for_update(normalized_email)
            if credential is None:
                _raise_login_failed()

            user = await _load_active_user(uow, user_id=credential.user_id)
            if user is None:
                _raise_login_failed()

            requires_rehash = await _verify_password_or_fail(
                self.password_hasher,
                candidate=plaintext_password,
                stored=credential,
            )

            if credential.email_verified_at is None:
                _raise_login_failed()

            if requires_rehash:
                await uow.credentials.replace_password_hash(
                    credential_id=credential.id,
                    password_hash=self.password_hasher.hash_password(plaintext_password),
                )

            if mfa_required:
                issued = issue_pending_mfa_session(
                    session_id=validated_session_id,
                    user_id=user.id,
                    issued_at=validated_authenticated_at,
                    raw_token_factory=raw_token_factory,
                    timeout_policy=self.session_timeout_policy,
                )
            else:
                issued = issue_authenticated_session(
                    session_id=validated_session_id,
                    user_id=user.id,
                    assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
                    issued_at=validated_authenticated_at,
                    raw_token_factory=raw_token_factory,
                    timeout_policy=self.session_timeout_policy,
                )

            await uow.sessions.add(issued.session)
            await uow.commit()

        return issued

    async def complete_mfa_login(
        self,
        *,
        pending_session_raw_token: RawAuthenticationToken,
        new_session_id: UUID,
        method: MfaMethod,
        mfa_response: object,
        completed_at: datetime,
        mfa_verifier: MfaVerifier,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> IssuedAuthenticationSession:
        if not isinstance(pending_session_raw_token, RawAuthenticationToken):
            raise TypeError("pending_session_raw_token must be a RawAuthenticationToken")

        validated_new_session_id = _validate_uuid(new_session_id, "new_session_id")
        validated_completed_at = _validate_timezone_aware_datetime(
            completed_at,
            "completed_at",
        )
        if not isinstance(method, MfaMethod):
            raise TypeError("method must be an MfaMethod")

        token_hash = hash_authentication_token(pending_session_raw_token)

        uow = self.uow_factory()
        async with uow:
            pending_session = await uow.sessions.get_by_token_hash_for_update(token_hash)
            if pending_session is None:
                _raise_unavailable()

            if pending_session.stage is not AuthenticationSessionStage.PENDING_MFA:
                _raise_unavailable()

            try:
                require_usable_authentication_session(
                    session=pending_session,
                    now=validated_completed_at,
                    policy=self.session_timeout_policy,
                )
            except AuthenticationSessionUnavailableError as error:
                raise AuthenticationWorkflowUnavailableError(
                    AUTHENTICATION_UNAVAILABLE_MESSAGE
                ) from error

            verified = await mfa_verifier.verify_mfa(
                user_id=pending_session.user_id,
                method=method,
                response=mfa_response,
            )
            if not verified:
                _raise_unavailable()

            try:
                rotation = complete_pending_mfa_and_rotate_session(
                    pending_session=pending_session,
                    new_session_id=validated_new_session_id,
                    completed_at=validated_completed_at,
                    raw_token_factory=raw_token_factory,
                    timeout_policy=self.session_timeout_policy,
                )
            except AuthenticationSessionTransitionError as error:
                raise AuthenticationWorkflowUnavailableError(
                    AUTHENTICATION_UNAVAILABLE_MESSAGE
                ) from error

            await uow.sessions.revoke(
                session_id=rotation.revoked_session.id,
                revoked_at=validated_completed_at,
            )
            await uow.sessions.add(rotation.issued.session)
            await uow.commit()

        return rotation.issued

    async def resolve_session(
        self,
        *,
        raw_token: RawAuthenticationToken,
        now: datetime,
        touch_session: bool = True,
    ) -> ResolvedAuthenticationSession:
        if not isinstance(raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")

        validated_now = _validate_timezone_aware_datetime(now, "now")
        token_hash = hash_authentication_token(raw_token)

        uow = self.uow_factory()
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
                    policy=self.session_timeout_policy,
                )
            except AuthenticationSessionUnavailableError as error:
                raise AuthenticationWorkflowUnavailableError(
                    AUTHENTICATION_UNAVAILABLE_MESSAGE
                ) from error

            user = await _load_active_user(uow, user_id=session.user_id)
            if user is None:
                _raise_unavailable()

            if touch_session and (
                validated_now - session.last_seen_at >= self.session_touch_interval
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

        return ResolvedAuthenticationSession(session=session, user=user)

    async def logout(
        self,
        *,
        raw_token: RawAuthenticationToken,
        revoked_at: datetime,
    ) -> None:
        if not isinstance(raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")

        validated_revoked_at = _validate_timezone_aware_datetime(
            revoked_at,
            "revoked_at",
        )
        token_hash = hash_authentication_token(raw_token)

        uow = self.uow_factory()
        async with uow:
            session = await uow.sessions.get_by_token_hash_for_update(token_hash)
            if session is not None and session.revoked_at is None:
                await uow.sessions.revoke(
                    session_id=session.id,
                    revoked_at=validated_revoked_at,
                )
            await uow.commit()

    async def logout_all_sessions(
        self,
        *,
        user_id: UUID,
        revoked_at: datetime,
    ) -> int:
        validated_user_id = _validate_uuid(user_id, "user_id")
        validated_revoked_at = _validate_timezone_aware_datetime(
            revoked_at,
            "revoked_at",
        )

        uow = self.uow_factory()
        async with uow:
            revoked_count = await uow.sessions.revoke_all_for_user(
                user_id=validated_user_id,
                revoked_at=validated_revoked_at,
            )
            await uow.commit()

        return revoked_count

    async def request_password_reset(
        self,
        *,
        email: str,
        reset_token_id: UUID,
        requested_at: datetime,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> AuthenticationRequestAccepted:
        validated_token_id = _validate_uuid(reset_token_id, "reset_token_id")
        validated_requested_at = _validate_timezone_aware_datetime(
            requested_at,
            "requested_at",
        )
        normalized_email = _normalize_email(email)

        uow = self.uow_factory()
        async with uow:
            credential = await uow.credentials.get_by_email(normalized_email)
            user = (
                await _load_active_user(uow, user_id=credential.user_id)
                if credential is not None
                else None
            )
            delivery: AuthenticationNotificationDelivery | None = None
            if _eligible_for_reset_delivery(user, credential):
                assert credential is not None
                delivery = await _issue_reset_delivery(
                    uow,
                    user_id=credential.user_id,
                    credential=credential,
                    reset_token_id=validated_token_id,
                    requested_at=validated_requested_at,
                    raw_token_factory=raw_token_factory,
                )
            await uow.commit()

        return AuthenticationRequestAccepted(delivery=delivery)

    async def confirm_password_reset(
        self,
        *,
        raw_token: RawAuthenticationToken,
        new_plaintext_password: str,
        confirmed_at: datetime,
    ) -> None:
        if not isinstance(raw_token, RawAuthenticationToken):
            raise TypeError("raw_token must be a RawAuthenticationToken")

        validated_confirmed_at = _validate_timezone_aware_datetime(
            confirmed_at,
            "confirmed_at",
        )
        token_hash = hash_authentication_token(raw_token)
        new_password_hash = self.password_hasher.hash_password(new_plaintext_password)

        uow = self.uow_factory()
        async with uow:
            token = await uow.one_time_tokens.get_by_token_hash_for_update(token_hash)
            if token is None:
                _raise_unavailable()

            await _consume_locked_one_time_token(
                uow,
                token=token,
                consumed_at=validated_confirmed_at,
                expected_purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
            )

            credential = await uow.credentials.get_by_user_id(token.user_id)
            if credential is None:
                _raise_unavailable()

            await uow.credentials.replace_password_hash(
                credential_id=credential.id,
                password_hash=new_password_hash,
            )
            await uow.one_time_tokens.revoke_active_for_user_and_purpose(
                user_id=token.user_id,
                purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
                revoked_at=validated_confirmed_at,
            )
            await uow.sessions.revoke_all_for_user(
                user_id=token.user_id,
                revoked_at=validated_confirmed_at,
            )
            await uow.commit()

    async def change_password(
        self,
        *,
        session_raw_token: RawAuthenticationToken,
        current_password: str,
        new_password: str,
        new_session_id: UUID,
        changed_at: datetime,
        raw_token_factory: _RawAuthenticationTokenFactory = (generate_raw_authentication_token),
    ) -> IssuedAuthenticationSession:
        if not isinstance(session_raw_token, RawAuthenticationToken):
            raise TypeError("session_raw_token must be a RawAuthenticationToken")

        validated_new_session_id = _validate_uuid(new_session_id, "new_session_id")
        validated_changed_at = _validate_timezone_aware_datetime(
            changed_at,
            "changed_at",
        )
        token_hash = hash_authentication_token(session_raw_token)

        uow = self.uow_factory()
        async with uow:
            session = await uow.sessions.get_by_token_hash_for_update(token_hash)
            if session is None:
                _raise_unavailable()

            if session.stage is not AuthenticationSessionStage.AUTHENTICATED:
                _raise_unavailable()

            try:
                require_usable_authentication_session(
                    session=session,
                    now=validated_changed_at,
                    policy=self.session_timeout_policy,
                )
            except AuthenticationSessionUnavailableError as error:
                raise AuthenticationWorkflowUnavailableError(
                    AUTHENTICATION_UNAVAILABLE_MESSAGE
                ) from error

            user = await _load_active_user(uow, user_id=session.user_id)
            if user is None:
                _raise_unavailable()

            credential = await uow.credentials.get_by_user_id(user.id)
            if credential is None:
                _raise_unavailable()

            await _verify_password_or_fail(
                self.password_hasher,
                candidate=current_password,
                stored=credential,
            )

            await uow.credentials.replace_password_hash(
                credential_id=credential.id,
                password_hash=self.password_hasher.hash_password(new_password),
            )
            await uow.sessions.revoke_all_for_user(
                user_id=user.id,
                revoked_at=validated_changed_at,
            )
            issued = issue_authenticated_session(
                session_id=validated_new_session_id,
                user_id=user.id,
                assurance_level=session.assurance_level,
                issued_at=validated_changed_at,
                raw_token_factory=raw_token_factory,
                timeout_policy=self.session_timeout_policy,
            )
            await uow.sessions.add(issued.session)
            await uow.commit()

        return issued


__all__ = [
    "AUTHENTICATION_FAILED_MESSAGE",
    "AUTHENTICATION_REQUEST_ACCEPTED_MESSAGE",
    "AUTHENTICATION_UNAVAILABLE_MESSAGE",
    "REGISTRATION_UNAVAILABLE_MESSAGE",
    "AuthenticationFailedError",
    "AuthenticationNotificationDelivery",
    "AuthenticationRequestAccepted",
    "AuthenticationWorkflowService",
    "AuthenticationWorkflowUnavailableError",
    "MfaVerifier",
    "RegistrationResult",
    "RegistrationUnavailableError",
    "ResolvedAuthenticationSession",
]
