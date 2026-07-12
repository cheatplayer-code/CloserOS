"""Unit tests for authentication workflow application layer."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from closeros.application.authentication_persistence import (
    DuplicateCredentialEmailError,
    DuplicateUserCredentialError,
)
from closeros.application.authentication_workflows import (
    AUTHENTICATION_FAILED_MESSAGE,
    AUTHENTICATION_UNAVAILABLE_MESSAGE,
    AuthenticationFailedError,
    AuthenticationNotificationDelivery,
    AuthenticationRequestAccepted,
    AuthenticationWorkflowService,
    AuthenticationWorkflowUnavailableError,
)
from closeros.domain.authentication import (
    AuthenticationEmail,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
    AuthenticationTokenPurpose,
    MfaMethod,
    PasswordHash,
)
from closeros.domain.authentication_session import AuthenticationSession
from closeros.domain.authentication_token import AuthenticationOneTimeToken
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import UserStatus
from closeros.domain.user import User
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.security.authentication_tokens import RawAuthenticationToken

from tests.auth_workflow_support import (
    AcceptingMfaVerifier,
    RejectingMfaVerifier,
    deterministic_token_factory,
    raw_token_from_entropy,
)

NOW = datetime(2026, 7, 12, 8, 0, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
CREDENTIAL_ID = UUID("00000000-0000-0000-0000-000000000020")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
NEW_SESSION_ID = UUID("00000000-0000-0000-0000-000000000101")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000200")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
EMAIL = AuthenticationEmail("unit.test@example.test")
PASSWORD = "Synthetic-Password-1"


@dataclass
class FakeState:
    users: dict[UUID, User] = field(default_factory=dict)
    credentials: dict[UUID, EmailPasswordCredential] = field(default_factory=dict)
    credentials_by_email: dict[str, UUID] = field(default_factory=dict)
    sessions: dict[UUID, AuthenticationSession] = field(default_factory=dict)
    sessions_by_hash: dict[bytes, UUID] = field(default_factory=dict)
    tokens: dict[UUID, AuthenticationOneTimeToken] = field(default_factory=dict)
    tokens_by_hash: dict[bytes, UUID] = field(default_factory=dict)
    committed: bool = False


class FakeUserRepository:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    async def add(self, user: User) -> None:
        self._state.users[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._state.users.get(user_id)

    async def update_status(self, *, user_id: UUID, status: UserStatus) -> None:
        user = self._state.users[user_id]
        self._state.users[user_id] = User(id=user.id, status=status)


class FakeCredentialRepository:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    async def add(self, credential: EmailPasswordCredential) -> None:
        if credential.email.value in self._state.credentials_by_email:
            raise DuplicateCredentialEmailError("duplicate")
        if any(item.user_id == credential.user_id for item in self._state.credentials.values()):
            raise DuplicateUserCredentialError("duplicate")
        self._state.credentials[credential.id] = credential
        self._state.credentials_by_email[credential.email.value] = credential.id

    async def get_by_id(self, credential_id: UUID) -> EmailPasswordCredential | None:
        return self._state.credentials.get(credential_id)

    async def get_by_user_id(self, user_id: UUID) -> EmailPasswordCredential | None:
        for credential in self._state.credentials.values():
            if credential.user_id == user_id:
                return credential
        return None

    async def get_by_email(self, email: AuthenticationEmail) -> EmailPasswordCredential | None:
        credential_id = self._state.credentials_by_email.get(email.value)
        return None if credential_id is None else self._state.credentials[credential_id]

    async def get_by_email_for_update(
        self,
        email: AuthenticationEmail,
    ) -> EmailPasswordCredential | None:
        return await self.get_by_email(email)

    async def set_email_verified_at(
        self,
        *,
        credential_id: UUID,
        verified_at: datetime,
    ) -> None:
        credential = self._state.credentials[credential_id]
        self._state.credentials[credential_id] = EmailPasswordCredential(
            id=credential.id,
            user_id=credential.user_id,
            email=credential.email,
            password_hash=credential.password_hash,
            created_at=credential.created_at,
            email_verified_at=verified_at,
        )

    async def replace_password_hash(
        self,
        *,
        credential_id: UUID,
        password_hash: PasswordHash,
    ) -> None:
        credential = self._state.credentials[credential_id]
        self._state.credentials[credential_id] = EmailPasswordCredential(
            id=credential.id,
            user_id=credential.user_id,
            email=credential.email,
            password_hash=password_hash,
            created_at=credential.created_at,
            email_verified_at=credential.email_verified_at,
        )


class FakeSessionRepository:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    async def add(self, session: AuthenticationSession) -> None:
        self._state.sessions[session.id] = session
        self._state.sessions_by_hash[session.token_hash.digest] = session.id

    async def get_by_id(self, session_id: UUID) -> AuthenticationSession | None:
        return self._state.sessions.get(session_id)

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationSession | None:
        session_id = self._state.sessions_by_hash.get(token_hash.digest)
        return None if session_id is None else self._state.sessions[session_id]

    async def get_by_token_hash_for_update(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationSession | None:
        return await self.get_by_token_hash(token_hash)

    async def list_active_for_user(
        self,
        *,
        user_id: UUID,
        now: datetime,
    ) -> tuple[AuthenticationSession, ...]:
        return tuple(
            session
            for session in self._state.sessions.values()
            if session.user_id == user_id
            and session.revoked_at is None
            and session.expires_at > now
        )

    async def update_last_seen(
        self,
        *,
        session_id: UUID,
        last_seen_at: datetime,
    ) -> None:
        session = self._state.sessions[session_id]
        self._state.sessions[session_id] = AuthenticationSession(
            id=session.id,
            user_id=session.user_id,
            token_hash=session.token_hash,
            stage=session.stage,
            assurance_level=session.assurance_level,
            mfa_completed=session.mfa_completed,
            created_at=session.created_at,
            last_seen_at=last_seen_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )

    async def revoke(self, *, session_id: UUID, revoked_at: datetime) -> None:
        session = self._state.sessions[session_id]
        if session.revoked_at is None:
            self._state.sessions[session_id] = AuthenticationSession(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                stage=session.stage,
                assurance_level=session.assurance_level,
                mfa_completed=session.mfa_completed,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                revoked_at=revoked_at,
            )

    async def revoke_all_for_user(
        self,
        *,
        user_id: UUID,
        revoked_at: datetime,
    ) -> int:
        count = 0
        for session_id, session in list(self._state.sessions.items()):
            if session.user_id == user_id and session.revoked_at is None:
                await self.revoke(session_id=session_id, revoked_at=revoked_at)
                count += 1
        return count


class FakeOneTimeTokenRepository:
    def __init__(self, state: FakeState) -> None:
        self._state = state

    async def add(self, token: AuthenticationOneTimeToken) -> None:
        self._state.tokens[token.id] = token
        self._state.tokens_by_hash[token.token_hash.digest] = token.id

    async def get_by_token_hash(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationOneTimeToken | None:
        token_id = self._state.tokens_by_hash.get(token_hash.digest)
        return None if token_id is None else self._state.tokens[token_id]

    async def get_by_token_hash_for_update(
        self,
        token_hash: AuthenticationTokenHash,
    ) -> AuthenticationOneTimeToken | None:
        return await self.get_by_token_hash(token_hash)

    async def consume(self, *, token_id: UUID, consumed_at: datetime) -> None:
        token = self._state.tokens[token_id]
        self._state.tokens[token_id] = AuthenticationOneTimeToken(
            id=token.id,
            user_id=token.user_id,
            purpose=token.purpose,
            token_hash=token.token_hash,
            created_at=token.created_at,
            expires_at=token.expires_at,
            consumed_at=consumed_at,
            revoked_at=token.revoked_at,
        )

    async def consume_if_usable(
        self,
        *,
        token_id: UUID,
        consumed_at: datetime,
        now: datetime,
    ) -> bool:
        token = self._state.tokens[token_id]
        if (
            token.consumed_at is not None
            or token.revoked_at is not None
            or now < token.created_at
            or now >= token.expires_at
        ):
            return False
        await self.consume(token_id=token_id, consumed_at=consumed_at)
        return True

    async def revoke(self, *, token_id: UUID, revoked_at: datetime) -> None:
        token = self._state.tokens[token_id]
        if token.revoked_at is None:
            self._state.tokens[token_id] = AuthenticationOneTimeToken(
                id=token.id,
                user_id=token.user_id,
                purpose=token.purpose,
                token_hash=token.token_hash,
                created_at=token.created_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=revoked_at,
            )

    async def revoke_active_for_user_and_purpose(
        self,
        *,
        user_id: UUID,
        purpose: AuthenticationTokenPurpose,
        revoked_at: datetime,
    ) -> int:
        count = 0
        for token_id, token in list(self._state.tokens.items()):
            if (
                token.user_id == user_id
                and token.purpose is purpose
                and token.revoked_at is None
                and token.consumed_at is None
            ):
                await self.revoke(token_id=token_id, revoked_at=revoked_at)
                count += 1
        return count


class FakeUnitOfWork:
    def __init__(self, state: FakeState) -> None:
        self._state = state
        self.users = FakeUserRepository(state)
        self.credentials = FakeCredentialRepository(state)
        self.sessions = FakeSessionRepository(state)
        self.one_time_tokens = FakeOneTimeTokenRepository(state)

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc is not None:
            self._state.committed = False

    async def commit(self) -> None:
        self._state.committed = True

    async def rollback(self) -> None:
        self._state.committed = False


def _service(state: FakeState | None = None) -> tuple[AuthenticationWorkflowService, FakeState]:
    fake_state = state or FakeState()
    service = AuthenticationWorkflowService(
        uow_factory=cast(Any, lambda: FakeUnitOfWork(fake_state)),
        password_hasher=Argon2idPasswordHasher(),
        session_touch_interval=timedelta(minutes=5),
    )
    return service, fake_state


async def _seed_verified_credential(state: FakeState) -> RawAuthenticationToken:
    service, _ = _service(state)
    registration = await service.register_user(
        user_id=USER_ID,
        credential_id=CREDENTIAL_ID,
        verification_token_id=TOKEN_ID,
        email=EMAIL.value,
        plaintext_password=PASSWORD,
        registered_at=NOW,
        raw_token_factory=deterministic_token_factory(bytes(range(32))),
    )
    await service.confirm_email_verification(
        raw_token=registration.delivery.raw_token,
        confirmed_at=NOW + timedelta(minutes=1),
    )
    return registration.delivery.raw_token


def test_delivery_repr_hides_recipient_and_token() -> None:
    raw_token = raw_token_from_entropy(bytes(range(32)))
    delivery = AuthenticationNotificationDelivery(
        recipient=EMAIL,
        raw_token=raw_token,
    )

    assert EMAIL.value not in repr(delivery)
    assert raw_token.value not in repr(delivery)


def test_request_accepted_repr_hides_delivery() -> None:
    accepted = AuthenticationRequestAccepted(
        delivery=AuthenticationNotificationDelivery(
            recipient=EMAIL,
            raw_token=raw_token_from_entropy(bytes(range(32))),
        )
    )

    assert EMAIL.value not in repr(accepted)


def test_application_workflows_module_has_no_infrastructure_imports() -> None:
    source = Path(
        "packages/backend/src/closeros/application/authentication_workflows.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    forbidden = (
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "closeros.infrastructure",
    )
    assert not any(name.startswith(forbidden) for name in imported)


def test_registration_success_commits_once() -> None:
    async def exercise() -> None:
        service, state = _service()
        result = await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=TOKEN_ID,
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(bytes(range(32))),
        )

        assert result.user_id == USER_ID
        assert state.committed is True
        assert USER_ID in state.users

    asyncio.run(exercise())


def test_verification_request_for_verified_account_has_no_delivery() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        accepted = await service.request_email_verification(
            email=EMAIL.value,
            verification_token_id=uuid4(),
            requested_at=NOW + timedelta(minutes=2),
        )

        assert accepted.delivery is None

    asyncio.run(exercise())


def test_login_failure_message_is_generic() -> None:
    async def exercise() -> None:
        service, _ = _service()

        with pytest.raises(AuthenticationFailedError) as exc_info:
            await service.login_with_password(
                email=EMAIL.value,
                plaintext_password=PASSWORD,
                session_id=SESSION_ID,
                authenticated_at=NOW,
                mfa_required=False,
            )

        assert str(exc_info.value) == AUTHENTICATION_FAILED_MESSAGE

    asyncio.run(exercise())


def test_login_success_after_verification() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        issued = await service.login_with_password(
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(bytes(reversed(range(32)))),
        )

        assert issued.session.stage is AuthenticationSessionStage.AUTHENTICATED

    asyncio.run(exercise())


def test_mfa_completion_failure_is_generic() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        pending = await service.login_with_password(
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(bytes(reversed(range(32)))),
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError) as exc_info:
            await service.complete_mfa_login(
                pending_session_raw_token=pending.raw_token,
                new_session_id=NEW_SESSION_ID,
                method=MfaMethod.TOTP,
                mfa_response={"code": "000000"},
                completed_at=NOW + timedelta(minutes=1),
                mfa_verifier=RejectingMfaVerifier(),
            )

        assert str(exc_info.value) == AUTHENTICATION_UNAVAILABLE_MESSAGE

    asyncio.run(exercise())


def test_mfa_completion_success_with_accepting_verifier() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        pending = await service.login_with_password(
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(bytes(reversed(range(32)))),
        )
        completed = await service.complete_mfa_login(
            pending_session_raw_token=pending.raw_token,
            new_session_id=NEW_SESSION_ID,
            method=MfaMethod.TOTP,
            mfa_response={"code": "123456"},
            completed_at=NOW + timedelta(minutes=1),
            mfa_verifier=AcceptingMfaVerifier(),
            raw_token_factory=deterministic_token_factory(
                bytes((index * 3) % 256 for index in range(32))
            ),
        )

        assert completed.session.stage is AuthenticationSessionStage.AUTHENTICATED
        assert completed.session.mfa_completed is True

    asyncio.run(exercise())


def test_resolve_session_skips_touch_within_interval() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        issued = await service.login_with_password(
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(bytes(reversed(range(32)))),
        )
        before = state.sessions[SESSION_ID].last_seen_at
        resolved = await service.resolve_session(
            raw_token=issued.raw_token,
            now=NOW + timedelta(minutes=1),
        )

        assert resolved.session.last_seen_at == before

    asyncio.run(exercise())


def test_reset_request_for_unverified_account_has_no_delivery() -> None:
    async def exercise() -> None:
        service, _ = _service()
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=TOKEN_ID,
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(bytes(range(32))),
        )
        accepted = await service.request_password_reset(
            email=EMAIL.value,
            reset_token_id=uuid4(),
            requested_at=NOW + timedelta(minutes=1),
        )

        assert accepted.delivery is None

    asyncio.run(exercise())


def test_change_password_wrong_current_password_fails_generically() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        issued = await service.login_with_password(
            email=EMAIL.value,
            plaintext_password=PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(bytes(reversed(range(32)))),
        )

        with pytest.raises(AuthenticationFailedError):
            await service.change_password(
                session_raw_token=issued.raw_token,
                current_password="wrong-password-value",
                new_password="Synthetic-Password-2",
                new_session_id=NEW_SESSION_ID,
                changed_at=NOW + timedelta(minutes=1),
            )

    asyncio.run(exercise())


def test_confirm_verification_with_wrong_purpose_token_fails() -> None:
    async def exercise() -> None:
        state = FakeState()
        service, _ = _service(state)
        await _seed_verified_credential(state)
        reset = await service.request_password_reset(
            email=EMAIL.value,
            reset_token_id=TOKEN_ID,
            requested_at=NOW + timedelta(hours=1),
            raw_token_factory=deterministic_token_factory(
                bytes((index * 5) % 256 for index in range(32))
            ),
        )
        assert reset.delivery is not None

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.confirm_email_verification(
                raw_token=reset.delivery.raw_token,
                confirmed_at=NOW + timedelta(hours=1, minutes=1),
            )

    asyncio.run(exercise())


def test_public_workflow_symbols_are_exported_from_application() -> None:
    from closeros import application

    assert "AuthenticationWorkflowService" in application.__all__
    assert "AuthenticationFailedError" in application.__all__
    assert "MfaVerifier" in application.__all__
