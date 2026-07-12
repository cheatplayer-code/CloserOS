"""PostgreSQL integration tests for authentication workflows."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from closeros.application.authentication_workflows import (
    AUTHENTICATION_FAILED_MESSAGE,
    AUTHENTICATION_UNAVAILABLE_MESSAGE,
    REGISTRATION_UNAVAILABLE_MESSAGE,
    AuthenticationFailedError,
    AuthenticationWorkflowService,
    AuthenticationWorkflowUnavailableError,
    RegistrationUnavailableError,
)
from closeros.domain.authentication import (
    AuthenticationEmail,
    AuthenticationSessionStage,
    MfaMethod,
)
from closeros.domain.email_password_credential import EmailPasswordCredential
from closeros.domain.identity import UserStatus
from closeros.domain.user import User
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher
from closeros.security.authentication_tokens import hash_authentication_token

from tests.auth_workflow_support import (
    CREDENTIAL_ID,
    NEW_SESSION_ID,
    NOW,
    OTHER_PASSWORD,
    OTHER_SESSION_ID,
    REGISTER_EMAIL,
    REGISTER_PASSWORD,
    RESET_TOKEN_ID,
    SESSION_ID,
    TEST_AUDIT_CONTEXT,
    TOKEN_ENTROPY_A,
    TOKEN_ENTROPY_B,
    TOKEN_ENTROPY_C,
    USER_ID,
    VERIFICATION_TOKEN_ID,
    AcceptingMfaVerifier,
    RejectingMfaVerifier,
    deterministic_token_factory,
    raw_token_from_entropy,
)

pytestmark = pytest.mark.auth_persistence


def _workflow_service(auth_uow_factory: Any) -> AuthenticationWorkflowService:
    return AuthenticationWorkflowService(
        uow_factory=auth_uow_factory,
        password_hasher=Argon2idPasswordHasher(),
        session_touch_interval=timedelta(minutes=5),
    )


async def _register_verified_user(
    service: AuthenticationWorkflowService,
    *,
    user_id: UUID = USER_ID,
    credential_id: UUID = CREDENTIAL_ID,
    verification_token_id: UUID = VERIFICATION_TOKEN_ID,
    email: str = REGISTER_EMAIL,
    password: str = REGISTER_PASSWORD,
    registered_at: Any = NOW,
    token_entropy: bytes = TOKEN_ENTROPY_A,
) -> tuple[Any, Any]:
    registration = await service.register_user(
        user_id=user_id,
        credential_id=credential_id,
        verification_token_id=verification_token_id,
        email=email,
        plaintext_password=password,
        registered_at=registered_at,
        raw_token_factory=deterministic_token_factory(token_entropy),
        audit_context=TEST_AUDIT_CONTEXT,
    )
    await service.confirm_email_verification(
        raw_token=registration.delivery.raw_token,
        confirmed_at=registered_at + timedelta(minutes=1),
        audit_context=TEST_AUDIT_CONTEXT,
    )
    return registration, registration.delivery.raw_token


def test_registration_persists_user_and_credential(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        registration = await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        lookup = auth_uow_factory()
        async with lookup:
            user = await lookup.users.get_by_id(USER_ID)
            credential = await lookup.credentials.get_by_user_id(USER_ID)

        assert registration.user_id == USER_ID
        assert user is not None
        assert user.status is UserStatus.ACTIVE
        assert credential is not None
        assert credential.email_verified_at is None
        assert REGISTER_PASSWORD not in repr(registration)
        assert registration.delivery.raw_token.value not in repr(registration)

    asyncio.run(exercise())


def test_registration_rejects_duplicate_email(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(RegistrationUnavailableError) as exc_info:
            await service.register_user(
                user_id=UUID("00000000-0000-0000-0000-000000000011"),
                credential_id=UUID("00000000-0000-0000-0000-000000000021"),
                verification_token_id=UUID("00000000-0000-0000-0000-000000000031"),
                email=REGISTER_EMAIL,
                plaintext_password=REGISTER_PASSWORD,
                registered_at=NOW,
                raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
                audit_context=TEST_AUDIT_CONTEXT,
            )

        assert str(exc_info.value) == REGISTRATION_UNAVAILABLE_MESSAGE
        assert REGISTER_EMAIL not in str(exc_info.value)

    asyncio.run(exercise())


def test_verification_request_is_generic_for_unknown_email(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        accepted = await service.request_email_verification(
            email="missing@example.test",
            verification_token_id=VERIFICATION_TOKEN_ID,
            requested_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert accepted.delivery is None
        assert accepted.message == "authentication request accepted"

    asyncio.run(exercise())


def test_verification_request_revokes_prior_tokens(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        first = await service.request_email_verification(
            email=REGISTER_EMAIL,
            verification_token_id=UUID("00000000-0000-0000-0000-000000000031"),
            requested_at=NOW + timedelta(minutes=1),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        second = await service.request_email_verification(
            email=REGISTER_EMAIL,
            verification_token_id=UUID("00000000-0000-0000-0000-000000000032"),
            requested_at=NOW + timedelta(minutes=2),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert first.delivery is not None
        assert second.delivery is not None
        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.confirm_email_verification(
                raw_token=first.delivery.raw_token,
                confirmed_at=NOW + timedelta(minutes=3),
                audit_context=TEST_AUDIT_CONTEXT,
            )

        await service.confirm_email_verification(
            raw_token=second.delivery.raw_token,
            confirmed_at=NOW + timedelta(minutes=3),
            audit_context=TEST_AUDIT_CONTEXT,
        )

    asyncio.run(exercise())


def test_confirm_email_verification_marks_credential_verified(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        registration = await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        confirmed_at = NOW + timedelta(minutes=5)
        await service.confirm_email_verification(
            raw_token=registration.delivery.raw_token,
            confirmed_at=confirmed_at,
            audit_context=TEST_AUDIT_CONTEXT,
        )

        lookup = auth_uow_factory()
        async with lookup:
            credential = await lookup.credentials.get_by_id(CREDENTIAL_ID)

        assert credential is not None
        assert credential.email_verified_at == confirmed_at

    asyncio.run(exercise())


def test_confirm_email_verification_rejects_replay(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        registration = await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        raw_token = registration.delivery.raw_token
        await service.confirm_email_verification(
            raw_token=raw_token,
            confirmed_at=NOW + timedelta(minutes=1),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.confirm_email_verification(
                raw_token=raw_token,
                confirmed_at=NOW + timedelta(minutes=2),
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_login_success_single_factor(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert issued.session.stage is AuthenticationSessionStage.AUTHENTICATED
        assert issued.raw_token.value not in repr(issued)

    asyncio.run(exercise())


def test_login_rejects_wrong_password(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)

        with pytest.raises(AuthenticationFailedError) as exc_info:
            await service.login_with_password(
                email=REGISTER_EMAIL,
                plaintext_password="wrong-password-value",
                session_id=SESSION_ID,
                authenticated_at=NOW + timedelta(hours=1),
                mfa_required=False,
                audit_context=TEST_AUDIT_CONTEXT,
            )

        assert str(exc_info.value) == AUTHENTICATION_FAILED_MESSAGE

    asyncio.run(exercise())


def test_login_rejects_unknown_email(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)

        with pytest.raises(AuthenticationFailedError):
            await service.login_with_password(
                email="missing@example.test",
                plaintext_password=REGISTER_PASSWORD,
                session_id=SESSION_ID,
                authenticated_at=NOW,
                mfa_required=False,
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_login_rejects_disabled_user(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)

        disable_uow = auth_uow_factory()
        async with disable_uow:
            await disable_uow.users.update_status(
                user_id=USER_ID,
                status=UserStatus.DISABLED,
            )
            await disable_uow.commit()

        with pytest.raises(AuthenticationFailedError):
            await service.login_with_password(
                email=REGISTER_EMAIL,
                plaintext_password=REGISTER_PASSWORD,
                session_id=SESSION_ID,
                authenticated_at=NOW + timedelta(hours=1),
                mfa_required=False,
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_login_rejects_unverified_email(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationFailedError):
            await service.login_with_password(
                email=REGISTER_EMAIL,
                plaintext_password=REGISTER_PASSWORD,
                session_id=SESSION_ID,
                authenticated_at=NOW + timedelta(hours=1),
                mfa_required=False,
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_login_pending_mfa_path(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert issued.session.stage is AuthenticationSessionStage.PENDING_MFA

    asyncio.run(exercise())


def test_mfa_completion_rotates_session(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        pending = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        completed = await service.complete_mfa_login(
            pending_session_raw_token=pending.raw_token,
            new_session_id=NEW_SESSION_ID,
            method=MfaMethod.TOTP,
            mfa_response={"code": "123456"},
            completed_at=NOW + timedelta(hours=1, minutes=1),
            mfa_verifier=AcceptingMfaVerifier(),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert completed.session.stage is AuthenticationSessionStage.AUTHENTICATED
        assert completed.session.mfa_completed is True
        assert completed.session.id == NEW_SESSION_ID
        assert completed.session.token_hash != pending.session.token_hash

    asyncio.run(exercise())


def test_mfa_completion_rejects_failed_verification(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        pending = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.complete_mfa_login(
                pending_session_raw_token=pending.raw_token,
                new_session_id=NEW_SESSION_ID,
                method=MfaMethod.TOTP,
                mfa_response={"code": "000000"},
                completed_at=NOW + timedelta(hours=1, minutes=1),
                mfa_verifier=RejectingMfaVerifier(),
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_mfa_completion_cannot_complete_twice(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        pending = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        await service.complete_mfa_login(
            pending_session_raw_token=pending.raw_token,
            new_session_id=NEW_SESSION_ID,
            method=MfaMethod.TOTP,
            mfa_response={"code": "123456"},
            completed_at=NOW + timedelta(hours=1, minutes=1),
            mfa_verifier=AcceptingMfaVerifier(),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.complete_mfa_login(
                pending_session_raw_token=pending.raw_token,
                new_session_id=OTHER_SESSION_ID,
                method=MfaMethod.TOTP,
                mfa_response={"code": "123456"},
                completed_at=NOW + timedelta(hours=1, minutes=2),
                mfa_verifier=AcceptingMfaVerifier(),
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_resolve_session_returns_active_user(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        resolved = await service.resolve_session(
            raw_token=issued.raw_token,
            now=NOW + timedelta(hours=1, minutes=1),
        )

        assert resolved.user.id == USER_ID
        assert resolved.session.id == SESSION_ID

    asyncio.run(exercise())


def test_resolve_session_rejects_expired_session(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.resolve_session(
                raw_token=issued.raw_token,
                now=NOW + timedelta(days=2),
            )

    asyncio.run(exercise())


def test_resolve_session_touches_after_interval(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        touch_at = NOW + timedelta(minutes=6)
        resolved = await service.resolve_session(
            raw_token=issued.raw_token,
            now=touch_at,
        )

        lookup = auth_uow_factory()
        async with lookup:
            stored = await lookup.sessions.get_by_id(SESSION_ID)

        assert resolved.session.last_seen_at == touch_at
        assert stored is not None
        assert stored.last_seen_at == touch_at
        assert stored.expires_at == issued.session.expires_at

    asyncio.run(exercise())


def test_logout_is_idempotent(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        revoked_at = NOW + timedelta(minutes=10)
        await service.logout(
            raw_token=issued.raw_token,
            revoked_at=revoked_at,
            audit_context=TEST_AUDIT_CONTEXT,
        )
        await service.logout(
            raw_token=issued.raw_token,
            revoked_at=revoked_at + timedelta(minutes=1),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        lookup = auth_uow_factory()
        async with lookup:
            stored = await lookup.sessions.get_by_id(SESSION_ID)

        assert stored is not None
        assert stored.revoked_at == revoked_at

    asyncio.run(exercise())


def test_logout_all_revokes_active_sessions(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=OTHER_SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        revoked_count = await service.logout_all_sessions(
            user_id=USER_ID,
            revoked_at=NOW + timedelta(minutes=1),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert revoked_count == 2

    asyncio.run(exercise())


def test_password_reset_request_is_generic_for_unknown_email(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        accepted = await service.request_password_reset(
            email="missing@example.test",
            reset_token_id=RESET_TOKEN_ID,
            requested_at=NOW,
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert accepted.delivery is None

    asyncio.run(exercise())


def test_password_reset_confirm_revokes_all_sessions(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        reset = await service.request_password_reset(
            email=REGISTER_EMAIL,
            reset_token_id=RESET_TOKEN_ID,
            requested_at=NOW + timedelta(minutes=1),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        assert reset.delivery is not None
        await service.confirm_password_reset(
            raw_token=reset.delivery.raw_token,
            new_plaintext_password=OTHER_PASSWORD,
            confirmed_at=NOW + timedelta(minutes=2),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        lookup = auth_uow_factory()
        async with lookup:
            active = await lookup.sessions.list_active_for_user(
                user_id=USER_ID,
                now=NOW + timedelta(minutes=3),
            )

        assert active == ()

    asyncio.run(exercise())


def test_password_reset_confirm_rejects_replay(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        reset = await service.request_password_reset(
            email=REGISTER_EMAIL,
            reset_token_id=RESET_TOKEN_ID,
            requested_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        assert reset.delivery is not None
        raw_token = reset.delivery.raw_token
        await service.confirm_password_reset(
            raw_token=raw_token,
            new_plaintext_password=OTHER_PASSWORD,
            confirmed_at=NOW + timedelta(minutes=1),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.confirm_password_reset(
                raw_token=raw_token,
                new_plaintext_password=REGISTER_PASSWORD,
                confirmed_at=NOW + timedelta(minutes=2),
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_change_password_rotates_session(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        pending = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=True,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        authenticated = await service.complete_mfa_login(
            pending_session_raw_token=pending.raw_token,
            new_session_id=NEW_SESSION_ID,
            method=MfaMethod.TOTP,
            mfa_response={"code": "123456"},
            completed_at=NOW + timedelta(minutes=1),
            mfa_verifier=AcceptingMfaVerifier(),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        rotated = await service.change_password(
            session_raw_token=authenticated.raw_token,
            current_password=REGISTER_PASSWORD,
            new_password=OTHER_PASSWORD,
            new_session_id=OTHER_SESSION_ID,
            changed_at=NOW + timedelta(minutes=2),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert rotated.session.mfa_completed is True
        assert rotated.session.id == OTHER_SESSION_ID

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.resolve_session(
                raw_token=authenticated.raw_token,
                now=NOW + timedelta(minutes=3),
            )

    asyncio.run(exercise())


def test_change_password_rejects_wrong_current_password(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        with pytest.raises(AuthenticationFailedError):
            await service.change_password(
                session_raw_token=issued.raw_token,
                current_password="wrong-password-value",
                new_password=OTHER_PASSWORD,
                new_session_id=NEW_SESSION_ID,
                changed_at=NOW + timedelta(minutes=1),
                audit_context=TEST_AUDIT_CONTEXT,
            )

    asyncio.run(exercise())


def test_consume_if_usable_prevents_duplicate_consumption(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        registration = await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        token_hash = hash_authentication_token(registration.delivery.raw_token)

        first = auth_uow_factory()
        second = auth_uow_factory()
        async with first, second:
            locked = await first.one_time_tokens.get_by_token_hash_for_update(token_hash)
            assert locked is not None
            consumed_once = await first.one_time_tokens.consume_if_usable(
                token_id=locked.id,
                consumed_at=NOW + timedelta(minutes=1),
                now=NOW + timedelta(minutes=1),
            )
            await first.commit()

            locked_again = await second.one_time_tokens.get_by_token_hash_for_update(token_hash)
            assert locked_again is not None
            consumed_twice = await second.one_time_tokens.consume_if_usable(
                token_id=locked_again.id,
                consumed_at=NOW + timedelta(minutes=2),
                now=NOW + timedelta(minutes=2),
            )
            await second.commit()

        assert consumed_once is True
        assert consumed_twice is False

    asyncio.run(exercise())


def test_verification_request_for_disabled_user_has_no_delivery(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await service.register_user(
            user_id=USER_ID,
            credential_id=CREDENTIAL_ID,
            verification_token_id=VERIFICATION_TOKEN_ID,
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            registered_at=NOW,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_A),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        disable_uow = auth_uow_factory()
        async with disable_uow:
            await disable_uow.users.update_status(
                user_id=USER_ID,
                status=UserStatus.DISABLED,
            )
            await disable_uow.commit()

        accepted = await service.request_email_verification(
            email=REGISTER_EMAIL,
            verification_token_id=UUID("00000000-0000-0000-0000-000000000033"),
            requested_at=NOW + timedelta(minutes=1),
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_B),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        assert accepted.delivery is None

    asyncio.run(exercise())


def test_login_rehash_updates_stored_password_hash(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        legacy_hasher = Argon2idPasswordHasher(memory_cost_kib=8 * 1024, time_cost=1)
        service = AuthenticationWorkflowService(
            uow_factory=auth_uow_factory,
            password_hasher=Argon2idPasswordHasher(),
            session_touch_interval=timedelta(minutes=5),
        )
        legacy_hash = legacy_hasher.hash_password(REGISTER_PASSWORD)

        seed_uow = auth_uow_factory()
        async with seed_uow:
            await seed_uow.users.add(User(id=USER_ID, status=UserStatus.ACTIVE))
            await seed_uow.credentials.add(
                EmailPasswordCredential(
                    id=CREDENTIAL_ID,
                    user_id=USER_ID,
                    email=AuthenticationEmail(REGISTER_EMAIL),
                    password_hash=legacy_hash,
                    created_at=NOW,
                    email_verified_at=NOW + timedelta(minutes=1),
                )
            )
            await seed_uow.commit()

        await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW + timedelta(hours=1),
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )

        lookup = auth_uow_factory()
        async with lookup:
            credential = await lookup.credentials.get_by_id(CREDENTIAL_ID)

        assert credential is not None
        assert credential.password_hash.encoded != legacy_hash.encoded
        assert credential.password_hash.encoded.startswith("$argon2id$")

    asyncio.run(exercise())


def test_resolve_session_rejects_disabled_user(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)
        issued = await service.login_with_password(
            email=REGISTER_EMAIL,
            plaintext_password=REGISTER_PASSWORD,
            session_id=SESSION_ID,
            authenticated_at=NOW,
            mfa_required=False,
            raw_token_factory=deterministic_token_factory(TOKEN_ENTROPY_C),
            audit_context=TEST_AUDIT_CONTEXT,
        )
        disable_uow = auth_uow_factory()
        async with disable_uow:
            await disable_uow.users.update_status(
                user_id=USER_ID,
                status=UserStatus.DISABLED,
            )
            await disable_uow.commit()

        with pytest.raises(AuthenticationWorkflowUnavailableError):
            await service.resolve_session(
                raw_token=issued.raw_token,
                now=NOW + timedelta(minutes=1),
            )

    asyncio.run(exercise())


def test_logout_unknown_token_does_not_raise(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await service.logout(
            raw_token=raw_token_from_entropy(TOKEN_ENTROPY_A),
            revoked_at=NOW,
            audit_context=TEST_AUDIT_CONTEXT,
        )

    asyncio.run(exercise())


def test_workflow_errors_do_not_leak_sensitive_values(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        service = _workflow_service(auth_uow_factory)
        await _register_verified_user(service)

        with pytest.raises(AuthenticationFailedError) as exc_info:
            await service.login_with_password(
                email=REGISTER_EMAIL,
                plaintext_password="wrong-password-value",
                session_id=SESSION_ID,
                authenticated_at=NOW,
                mfa_required=False,
                audit_context=TEST_AUDIT_CONTEXT,
            )

        error_text = f"{exc_info.value}{repr(exc_info.value)}"
        assert REGISTER_EMAIL not in error_text
        assert REGISTER_PASSWORD not in error_text
        assert AUTHENTICATION_UNAVAILABLE_MESSAGE not in error_text

    asyncio.run(exercise())
