"""Tests for authentication unit-of-work transaction boundaries."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from closeros.application.authentication_persistence import DuplicateCredentialEmailError
from closeros.infrastructure.authentication_unit_of_work import UnitOfWorkStateError

from tests.auth_persistence_support import (
    OTHER_USER_ID,
    USER_ID,
    synthetic_credential,
    synthetic_user,
)

pytestmark = pytest.mark.auth_persistence


async def _seed_user(uow: Any, *, user_id: UUID = USER_ID) -> None:
    await uow.users.add(synthetic_user(user_id=user_id))
    await uow.commit()


def test_unit_of_work_commits_persisted_user(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            restored = await lookup.users.get_by_id(synthetic_user().id)

        assert restored is not None

    asyncio.run(exercise())


def test_unit_of_work_rolls_back_after_exception(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        with pytest.raises(DuplicateCredentialEmailError):
            async with uow:
                await uow.users.add(synthetic_user(user_id=USER_ID))
                await uow.users.add(synthetic_user(user_id=OTHER_USER_ID))
                await uow.credentials.add(synthetic_credential())
                await uow.credentials.add(
                    synthetic_credential(
                        credential_id=UUID("00000000-0000-0000-0000-000000000021"),
                        user_id=OTHER_USER_ID,
                        email=synthetic_credential().email,
                    )
                )
                await uow.commit()

        lookup = auth_uow_factory()
        async with lookup:
            user = await lookup.users.get_by_id(synthetic_user().id)
            credential = await lookup.credentials.get_by_user_id(synthetic_user().id)

        assert user is None
        assert credential is None

    asyncio.run(exercise())


def test_unit_of_work_explicit_rollback_discards_changes(auth_uow_factory: Any) -> None:
    async def exercise() -> None:
        uow = auth_uow_factory()
        async with uow:
            await uow.users.add(synthetic_user())
            await uow.rollback()

        lookup = auth_uow_factory()
        async with lookup:
            restored = await lookup.users.get_by_id(synthetic_user().id)

        assert restored is None

    asyncio.run(exercise())


def test_unit_of_work_commit_outside_context_raises(auth_uow_factory: Any) -> None:
    uow = auth_uow_factory()

    with pytest.raises(UnitOfWorkStateError):
        asyncio.run(uow.commit())
