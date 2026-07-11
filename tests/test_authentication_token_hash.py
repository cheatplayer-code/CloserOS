"""Tests for CLS-011.2b authentication token hash value object."""

# mypy: disable-error-code=import-untyped

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from closeros.domain import AuthenticationTokenHash

DIGEST = bytes(range(32))
OTHER_DIGEST = bytes(reversed(range(32)))


def test_32_byte_digest_is_accepted_and_stored_unchanged() -> None:
    token_hash = AuthenticationTokenHash(digest=DIGEST)

    assert token_hash.digest == DIGEST


def test_another_32_byte_digest_is_accepted() -> None:
    token_hash = AuthenticationTokenHash(digest=OTHER_DIGEST)

    assert token_hash.digest == OTHER_DIGEST


def test_empty_bytes_raise_value_error() -> None:
    with pytest.raises(ValueError, match="digest must contain exactly 32 bytes"):
        AuthenticationTokenHash(digest=b"")


def test_31_byte_digest_raises_value_error() -> None:
    with pytest.raises(ValueError, match="digest must contain exactly 32 bytes"):
        AuthenticationTokenHash(digest=b"a" * 31)


def test_33_byte_digest_raises_value_error() -> None:
    with pytest.raises(ValueError, match="digest must contain exactly 32 bytes"):
        AuthenticationTokenHash(digest=b"a" * 33)


def test_bytearray_raises_type_error() -> None:
    with pytest.raises(TypeError, match="digest must be bytes"):
        AuthenticationTokenHash(digest=cast(Any, bytearray(DIGEST)))


def test_memoryview_raises_type_error() -> None:
    with pytest.raises(TypeError, match="digest must be bytes"):
        AuthenticationTokenHash(digest=cast(Any, memoryview(DIGEST)))


def test_str_raises_type_error() -> None:
    with pytest.raises(TypeError, match="digest must be bytes"):
        AuthenticationTokenHash(digest=cast(Any, "digest"))


def test_none_raises_type_error() -> None:
    with pytest.raises(TypeError, match="digest must be bytes"):
        AuthenticationTokenHash(digest=cast(Any, None))


def test_authentication_token_hash_is_immutable() -> None:
    token_hash = AuthenticationTokenHash(digest=DIGEST)

    with pytest.raises(FrozenInstanceError):
        cast(Any, token_hash).digest = OTHER_DIGEST


def test_repr_hides_digest_bytes_and_hex() -> None:
    token_hash_repr = repr(AuthenticationTokenHash(digest=DIGEST))

    assert repr(DIGEST) not in token_hash_repr
    assert DIGEST.hex() not in token_hash_repr


def test_authentication_token_hash_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationTokenHash.__name__ == "AuthenticationTokenHash"
