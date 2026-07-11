"""Tests for CLS-011.2e password hash value object."""

# mypy: disable-error-code=import-untyped

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from closeros.domain import PasswordHash

VALID_ENCODED = (
    "$argon2id$v=19$m=19456,t=2,p=1$c2FsdHNhbHQ$ZGlnaWVzdGRpZ2VzdGRpZ2VzdA"
)
OTHER_VALID_ENCODED = (
    "$argon2id$v=19$m=65536,t=3,p=4$YW5vdGhlcnNhbHQ$YW5vdGhlcmRpZ2VzdGRpZ2VzdA"
)


def test_valid_argon2id_phc_string_is_accepted() -> None:
    password_hash = PasswordHash(encoded=VALID_ENCODED)

    assert password_hash.encoded == VALID_ENCODED


def test_encoded_string_is_stored_unchanged() -> None:
    password_hash = PasswordHash(encoded=VALID_ENCODED)

    assert password_hash.encoded is VALID_ENCODED


def test_another_deterministic_argon2id_string_is_accepted() -> None:
    password_hash = PasswordHash(encoded=OTHER_VALID_ENCODED)

    assert password_hash.encoded == OTHER_VALID_ENCODED


def test_empty_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must not be empty"):
        PasswordHash(encoded="")


def test_whitespace_only_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must not contain surrounding whitespace"):
        PasswordHash(encoded="   ")


def test_leading_whitespace_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must not contain surrounding whitespace"):
        PasswordHash(encoded=f" {VALID_ENCODED}")


def test_trailing_whitespace_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must not contain surrounding whitespace"):
        PasswordHash(encoded=f"{VALID_ENCODED} ")


def test_internal_whitespace_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must not contain whitespace"):
        PasswordHash(
            encoded=VALID_ENCODED.replace(
                "c2FsdHNhbHQ",
                "c2Fs dHNhbHQ",
            )
        )


def test_argon2i_prefix_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must be an Argon2id PHC string"):
        PasswordHash(encoded=VALID_ENCODED.replace("$argon2id$", "$argon2i$"))


def test_argon2d_prefix_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must be an Argon2id PHC string"):
        PasswordHash(encoded=VALID_ENCODED.replace("$argon2id$", "$argon2d$"))


def test_bcrypt_like_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must be an Argon2id PHC string"):
        PasswordHash(encoded="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G2oQZqKqKqKqKq")


def test_plain_arbitrary_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="encoded must be an Argon2id PHC string"):
        PasswordHash(encoded="not-a-password-hash")


def test_bytes_raise_type_error() -> None:
    with pytest.raises(TypeError, match="encoded must be a string"):
        PasswordHash(encoded=cast(Any, VALID_ENCODED.encode()))


def test_none_raises_type_error() -> None:
    with pytest.raises(TypeError, match="encoded must be a string"):
        PasswordHash(encoded=cast(Any, None))


def test_password_hash_is_immutable() -> None:
    password_hash = PasswordHash(encoded=VALID_ENCODED)

    with pytest.raises(FrozenInstanceError):
        cast(Any, password_hash).encoded = OTHER_VALID_ENCODED


def test_repr_does_not_contain_encoded_hash() -> None:
    password_hash_repr = repr(PasswordHash(encoded=VALID_ENCODED))

    assert VALID_ENCODED not in password_hash_repr


def test_repr_does_not_contain_recognizable_phc_segments() -> None:
    password_hash_repr = repr(PasswordHash(encoded=VALID_ENCODED))

    assert "$argon2id$" not in password_hash_repr
    assert "c2FsdHNhbHQ" not in password_hash_repr
    assert "ZGlnaWVzdGRpZ2VzdGRpZ2VzdA" not in password_hash_repr


def test_password_hash_can_be_imported_from_closeros_domain() -> None:
    assert PasswordHash.__name__ == "PasswordHash"
