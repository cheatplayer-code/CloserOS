"""Tests for the Argon2id password hashing adapter."""

# mypy: disable-error-code=import-untyped

from typing import Any, cast

import pytest
from argon2 import PasswordHasher as RawArgon2Hasher
from argon2 import Type as Argon2Type
from closeros.domain.authentication import PasswordHash
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher

SYNTHETIC_PASSWORD = "synthetic-test-password-7f3a"
OTHER_PASSWORD = "other-synthetic-password-9c2e"


def _legacy_password_hash(plaintext: str) -> PasswordHash:
    legacy_hasher = RawArgon2Hasher(
        time_cost=2,
        memory_cost=8192,
        parallelism=1,
        type=Argon2Type.ID,
    )
    return PasswordHash(encoded=legacy_hasher.hash(plaintext))


def test_hash_password_returns_valid_password_hash() -> None:
    hasher = Argon2idPasswordHasher()
    password_hash = hasher.hash_password(SYNTHETIC_PASSWORD)

    assert isinstance(password_hash, PasswordHash)
    assert password_hash.encoded.startswith("$argon2id$")


def test_verify_password_accepts_matching_candidate() -> None:
    hasher = Argon2idPasswordHasher()
    stored = hasher.hash_password(SYNTHETIC_PASSWORD)

    result = hasher.verify_password(candidate=SYNTHETIC_PASSWORD, stored=stored)

    assert result.is_valid is True
    assert result.requires_rehash is False


def test_verify_password_rejects_incorrect_candidate() -> None:
    hasher = Argon2idPasswordHasher()
    stored = hasher.hash_password(SYNTHETIC_PASSWORD)

    result = hasher.verify_password(candidate=OTHER_PASSWORD, stored=stored)

    assert result.is_valid is False
    assert result.requires_rehash is False


def test_verify_password_detects_rehash_for_legacy_parameters() -> None:
    hasher = Argon2idPasswordHasher()
    stored = _legacy_password_hash(SYNTHETIC_PASSWORD)

    result = hasher.verify_password(candidate=SYNTHETIC_PASSWORD, stored=stored)

    assert result.is_valid is True
    assert result.requires_rehash is True


def test_verify_password_fails_safely_for_malformed_stored_hash() -> None:
    hasher = Argon2idPasswordHasher()
    stored = PasswordHash("$argon2id$v=19$m=19456,t=2,p=1$bad$bad")

    result = hasher.verify_password(candidate=SYNTHETIC_PASSWORD, stored=stored)

    assert result.is_valid is False
    assert result.requires_rehash is False


def test_repr_and_exceptions_do_not_leak_secrets() -> None:
    hasher = Argon2idPasswordHasher()
    stored = hasher.hash_password(SYNTHETIC_PASSWORD)

    assert SYNTHETIC_PASSWORD not in repr(hasher)
    assert stored.encoded not in repr(hasher)

    with pytest.raises(TypeError, match="plaintext must be a string"):
        hasher.hash_password(cast(Any, b"not-a-string"))


def test_rehash_produces_new_valid_hash() -> None:
    hasher = Argon2idPasswordHasher()
    legacy = _legacy_password_hash(SYNTHETIC_PASSWORD)
    replacement = hasher.hash_password(SYNTHETIC_PASSWORD)

    legacy_result = hasher.verify_password(
        candidate=SYNTHETIC_PASSWORD,
        stored=legacy,
    )
    replacement_result = hasher.verify_password(
        candidate=SYNTHETIC_PASSWORD,
        stored=replacement,
    )

    assert legacy_result.requires_rehash is True
    assert replacement_result.is_valid is True
    assert replacement_result.requires_rehash is False
