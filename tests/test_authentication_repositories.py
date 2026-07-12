"""PostgreSQL integration tests for authentication repositories."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from closeros.application.authentication_persistence import (
    AuthenticationRecordNotFoundError,
    AuthenticationReferenceError,
    DuplicateCredentialEmailError,
    DuplicateOneTimeTokenError,
    DuplicateSessionTokenError,
    DuplicateUserCredentialError,
)
from closeros.domain.authentication import AuthenticationTokenPurpose
from closeros.domain.identity import UserStatus
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher

from tests.auth_persistence_support import (
    CREDENTIAL_ID,
    NOW,
    OTHER_EMAIL,
    OTHER_SESSION_ID,
    OTHER_TOKEN_ID,
    OTHER_USER_ID,
    SESSION_ID,
    TOKEN_HASH_B,
    USER_ID,
    synthetic_credential,
    synthetic_one_time_token,
    synthetic_session,
    synthetic_user,
)

pytestmark = pytest.mark.auth_persistence


async def _seed_user(uow: Any, *, user_id: UUID = USER_ID) -> None:
    await uow.users.add(synthetic_user(user_id=user_id))
    await uow.commit()


def test_user_repository_add_and_get(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            restored = await lookup.users.get_by_id(USER_ID)

        assert restored is not None
        assert restored.status is UserStatus.ACTIVE

    asyncio.run(exercise())


def test_user_repository_update_status(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.users.update_status(user_id=USER_ID, status=UserStatus.DISABLED)
            await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            restored = await lookup.users.get_by_id(USER_ID)

        assert restored is not None
        assert restored.status is UserStatus.DISABLED

    asyncio.run(exercise())


def test_credential_repository_round_trip_and_email_lookup(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.credentials.add(synthetic_credential())
            await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            by_user = await lookup.credentials.get_by_user_id(USER_ID)
            by_email = await lookup.credentials.get_by_email(synthetic_credential().email)

        assert by_user is not None
        assert by_email is not None
        assert by_user.id == CREDENTIAL_ID
        assert by_email.email.value == synthetic_credential().email.value

    asyncio.run(exercise())


def test_credential_repository_enforces_unique_email(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await _seed_user(uow, user_id=OTHER_USER_ID)
            await uow.credentials.add(synthetic_credential())
            with pytest.raises(DuplicateCredentialEmailError):
                await uow.credentials.add(
                    synthetic_credential(
                        credential_id=UUID("00000000-0000-0000-0000-000000000021"),
                        user_id=OTHER_USER_ID,
                        email=synthetic_credential().email,
                    )
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_credential_repository_enforces_one_credential_per_user(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.credentials.add(synthetic_credential())
            with pytest.raises(DuplicateUserCredentialError):
                await uow.credentials.add(
                    synthetic_credential(
                        credential_id=UUID("00000000-0000-0000-0000-000000000021"),
                        email=OTHER_EMAIL,
                    )
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_credential_repository_rejects_missing_user(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            with pytest.raises(AuthenticationReferenceError):
                await uow.credentials.add(synthetic_credential())
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_credential_repository_updates_verification_and_password_hash(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        verified_at = NOW + timedelta(minutes=5)
        hasher = Argon2idPasswordHasher()
        replacement = hasher.hash_password("replacement-password-4d2c")

        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.credentials.add(synthetic_credential())
            await uow.commit()

        update = auth_uow_factory()
        async with update:
            await update.credentials.set_email_verified_at(
                credential_id=CREDENTIAL_ID,
                verified_at=verified_at,
            )
            await update.credentials.replace_password_hash(
                credential_id=CREDENTIAL_ID,
                password_hash=replacement,
            )
            await update.commit()

        lookup = auth_uow_factory()
        async with lookup:
            restored = await lookup.credentials.get_by_id(CREDENTIAL_ID)

        assert restored is not None
        assert restored.email_verified_at == verified_at
        assert restored.password_hash.encoded == replacement.encoded

    asyncio.run(exercise())


def test_session_repository_token_hash_lookup_and_active_list(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.sessions.add(synthetic_session())
            await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            by_hash = await lookup.sessions.get_by_token_hash(synthetic_session().token_hash)
            active = await lookup.sessions.list_active_for_user(
                user_id=USER_ID,
                now=NOW + timedelta(minutes=1),
            )

        assert by_hash is not None
        assert by_hash.id == SESSION_ID
        assert len(active) == 1

    asyncio.run(exercise())


def test_session_repository_enforces_unique_token_hash(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.sessions.add(synthetic_session())
            with pytest.raises(DuplicateSessionTokenError):
                await uow.sessions.add(
                    synthetic_session(
                        session_id=OTHER_SESSION_ID,
                        token_hash=synthetic_session().token_hash,
                    )
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_session_repository_revoke_operations(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        revoked_at = NOW + timedelta(minutes=30)

        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.sessions.add(synthetic_session())
            await uow.sessions.add(
                synthetic_session(
                    session_id=OTHER_SESSION_ID,
                    token_hash=TOKEN_HASH_B,
                )
            )
            await uow.commit()

        revoke = auth_uow_factory()
        async with revoke:
            await revoke.sessions.revoke(session_id=SESSION_ID, revoked_at=revoked_at)
            count = await revoke.sessions.revoke_all_for_user(
                user_id=USER_ID,
                revoked_at=revoked_at + timedelta(minutes=1),
            )
            await revoke.commit()

        lookup = auth_uow_factory()
        async with lookup:
            active = await lookup.sessions.list_active_for_user(
                user_id=USER_ID,
                now=NOW + timedelta(minutes=1),
            )

        assert count == 1
        assert active == ()

    asyncio.run(exercise())


def test_one_time_token_repository_consume_and_revoke_active(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        consumed_at = NOW + timedelta(minutes=10)
        revoked_at = NOW + timedelta(minutes=1)

        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.one_time_tokens.add(synthetic_one_time_token())
            await uow.one_time_tokens.add(
                synthetic_one_time_token(
                    token_id=OTHER_TOKEN_ID,
                    token_hash=TOKEN_HASH_B,
                )
            )
            await uow.commit()

        update = auth_uow_factory()
        async with update:
            revoked_count = await update.one_time_tokens.revoke_active_for_user_and_purpose(
                user_id=USER_ID,
                purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
                revoked_at=revoked_at,
            )
            await update.one_time_tokens.consume(
                token_id=OTHER_TOKEN_ID,
                consumed_at=consumed_at,
            )
            await update.commit()

        lookup = auth_uow_factory()
        async with lookup:
            first = await lookup.one_time_tokens.get_by_token_hash(
                synthetic_one_time_token().token_hash
            )
            second = await lookup.one_time_tokens.get_by_token_hash(TOKEN_HASH_B)

        assert revoked_count == 2
        assert first is not None
        assert first.revoked_at == revoked_at
        assert second is not None
        assert second.consumed_at == consumed_at

    asyncio.run(exercise())


def test_one_time_token_repository_enforces_unique_token_hash(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await uow.one_time_tokens.add(synthetic_one_time_token())
            with pytest.raises(DuplicateOneTimeTokenError):
                await uow.one_time_tokens.add(
                    synthetic_one_time_token(
                        token_id=OTHER_TOKEN_ID,
                        token_hash=synthetic_one_time_token().token_hash,
                    )
                )
                await uow.commit()
            await uow.rollback()

    asyncio.run(exercise())


def test_repository_update_missing_record_raises_not_found(
    auth_uow_factory: Any,
) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            with pytest.raises(AuthenticationRecordNotFoundError):
                await uow.credentials.set_email_verified_at(
                    credential_id=CREDENTIAL_ID,
                    verified_at=NOW,
                )

    asyncio.run(exercise())


def test_integrity_errors_do_not_leak_sensitive_values(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await _seed_user(uow)
            await _seed_user(uow, user_id=OTHER_USER_ID)
            await uow.credentials.add(synthetic_credential())
            try:
                await uow.credentials.add(
                    synthetic_credential(
                        credential_id=UUID("00000000-0000-0000-0000-000000000021"),
                        user_id=OTHER_USER_ID,
                        email=synthetic_credential().email,
                    )
                )
                await uow.commit()
            except DuplicateCredentialEmailError as error:
                message = str(error)
                assert synthetic_credential().email.value not in message
                assert synthetic_credential().password_hash.encoded not in message
            else:
                raise AssertionError("expected duplicate email error")

    asyncio.run(exercise())
