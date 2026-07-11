"""Tests for CLS-011.3e secure authentication token adapter."""

# mypy: disable-error-code=import-untyped

from base64 import urlsafe_b64encode
from dataclasses import FrozenInstanceError
from hashlib import sha256
from typing import Any, cast

import pytest
from closeros.domain.authentication import AuthenticationTokenHash
from closeros.security import (
    RawAuthenticationToken,
    authentication_token_matches_hash,
    generate_raw_authentication_token,
    hash_authentication_token,
)
from closeros.security import authentication_tokens as authentication_tokens_module

DETERMINISTIC_ENTROPY = bytes(range(32))
OTHER_DETERMINISTIC_ENTROPY = bytes(reversed(range(32)))
ENTROPY_WITH_URLSAFE_SPECIALS = bytes(byte ^ 0xFF for byte in range(32))

CANONICAL_TOKEN_VALUE = urlsafe_b64encode(DETERMINISTIC_ENTROPY).rstrip(b"=").decode("ascii")
OTHER_CANONICAL_TOKEN_VALUE = (
    urlsafe_b64encode(OTHER_DETERMINISTIC_ENTROPY).rstrip(b"=").decode("ascii")
)
TOKEN_WITH_URLSAFE_SPECIALS = (
    urlsafe_b64encode(ENTROPY_WITH_URLSAFE_SPECIALS).rstrip(b"=").decode("ascii")
)
NON_CANONICAL_TOKEN_VALUE = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHhd"


def test_raw_authentication_token_accepts_canonical_encoding() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)

    assert token.value == CANONICAL_TOKEN_VALUE
    assert len(token.value) == 43


def test_raw_authentication_token_accepts_urlsafe_dash_and_underscore() -> None:
    token = RawAuthenticationToken(TOKEN_WITH_URLSAFE_SPECIALS)

    assert "-" in token.value
    assert "_" in token.value
    assert token.value == TOKEN_WITH_URLSAFE_SPECIALS


def test_raw_authentication_token_rejects_bytes_type() -> None:
    with pytest.raises(TypeError, match="value must be a string"):
        RawAuthenticationToken(cast(Any, DETERMINISTIC_ENTROPY))


def test_raw_authentication_token_rejects_none() -> None:
    with pytest.raises(TypeError, match="value must be a string"):
        RawAuthenticationToken(cast(Any, None))


def test_raw_authentication_token_rejects_empty_string() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken("")


def test_raw_authentication_token_rejects_42_character_value() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(CANONICAL_TOKEN_VALUE[:-1])


def test_raw_authentication_token_rejects_44_character_value() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(f"{CANONICAL_TOKEN_VALUE}A")


def test_raw_authentication_token_rejects_padding() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(f"{CANONICAL_TOKEN_VALUE}=")


def test_raw_authentication_token_rejects_whitespace() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(f"{CANONICAL_TOKEN_VALUE[:21]} {CANONICAL_TOKEN_VALUE[21:]}")


def test_raw_authentication_token_rejects_slash() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(f"{CANONICAL_TOKEN_VALUE[:21]}/{CANONICAL_TOKEN_VALUE[22:]}")


def test_raw_authentication_token_rejects_plus() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(f"{CANONICAL_TOKEN_VALUE[:21]}+{CANONICAL_TOKEN_VALUE[22:]}")


def test_raw_authentication_token_rejects_non_canonical_value() -> None:
    with pytest.raises(
        ValueError,
        match="value must be a canonical URL-safe encoding of exactly 32 bytes",
    ):
        RawAuthenticationToken(NON_CANONICAL_TOKEN_VALUE)


def test_raw_authentication_token_is_immutable() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)

    with pytest.raises(FrozenInstanceError):
        cast(Any, token).value = OTHER_CANONICAL_TOKEN_VALUE


def test_repr_hides_raw_token_value() -> None:
    token_repr = repr(RawAuthenticationToken(CANONICAL_TOKEN_VALUE))

    assert CANONICAL_TOKEN_VALUE not in token_repr


def test_generation_requests_exactly_32_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_sizes: list[int] = []

    def fake_token_bytes(size: int) -> bytes:
        requested_sizes.append(size)
        return DETERMINISTIC_ENTROPY

    monkeypatch.setattr(
        authentication_tokens_module,
        "token_bytes",
        fake_token_bytes,
    )

    generate_raw_authentication_token()

    assert requested_sizes == [32]


def test_generation_produces_expected_deterministic_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authentication_tokens_module,
        "token_bytes",
        lambda _size: DETERMINISTIC_ENTROPY,
    )

    token = generate_raw_authentication_token()

    assert token.value == CANONICAL_TOKEN_VALUE
    assert len(token.value) == 43


def test_generated_token_contains_only_urlsafe_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authentication_tokens_module,
        "token_bytes",
        lambda _size: DETERMINISTIC_ENTROPY,
    )

    token = generate_raw_authentication_token()

    assert all(
        character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in token.value
    )


def test_different_entropy_produces_different_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entropy_inputs = iter([DETERMINISTIC_ENTROPY, OTHER_DETERMINISTIC_ENTROPY])

    monkeypatch.setattr(
        authentication_tokens_module,
        "token_bytes",
        lambda _size: next(entropy_inputs),
    )

    first_token = generate_raw_authentication_token()
    second_token = generate_raw_authentication_token()

    assert first_token.value == CANONICAL_TOKEN_VALUE
    assert second_token.value == OTHER_CANONICAL_TOKEN_VALUE
    assert first_token.value != second_token.value


def test_hash_authentication_token_returns_authentication_token_hash() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)

    token_hash = hash_authentication_token(token)

    assert isinstance(token_hash, AuthenticationTokenHash)


def test_hash_authentication_token_matches_sha256_ascii_digest() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)
    expected_digest = sha256(token.value.encode("ascii")).digest()

    token_hash = hash_authentication_token(token)

    assert token_hash.digest == expected_digest
    assert len(token_hash.digest) == 32


def test_hash_authentication_token_is_deterministic() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)

    first_hash = hash_authentication_token(token)
    second_hash = hash_authentication_token(token)

    assert first_hash.digest == second_hash.digest


def test_different_raw_tokens_produce_different_hashes() -> None:
    first_token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)
    second_token = RawAuthenticationToken(OTHER_CANONICAL_TOKEN_VALUE)

    first_hash = hash_authentication_token(first_token)
    second_hash = hash_authentication_token(second_token)

    assert first_hash.digest != second_hash.digest


def test_hash_authentication_token_rejects_wrong_token_type() -> None:
    with pytest.raises(TypeError, match="token must be a RawAuthenticationToken"):
        hash_authentication_token(cast(Any, CANONICAL_TOKEN_VALUE))


def test_authentication_token_matches_hash_returns_true_for_matching_token() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)
    expected_hash = hash_authentication_token(token)

    assert (
        authentication_token_matches_hash(
            token=token,
            expected_hash=expected_hash,
        )
        is True
    )


def test_authentication_token_matches_hash_returns_false_for_different_token() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)
    other_token = RawAuthenticationToken(OTHER_CANONICAL_TOKEN_VALUE)
    expected_hash = hash_authentication_token(token)

    assert (
        authentication_token_matches_hash(
            token=other_token,
            expected_hash=expected_hash,
        )
        is False
    )


def test_authentication_token_matches_hash_rejects_wrong_token_type() -> None:
    expected_hash = hash_authentication_token(RawAuthenticationToken(CANONICAL_TOKEN_VALUE))

    with pytest.raises(TypeError, match="token must be a RawAuthenticationToken"):
        authentication_token_matches_hash(
            token=cast(Any, CANONICAL_TOKEN_VALUE),
            expected_hash=expected_hash,
        )


def test_authentication_token_matches_hash_rejects_wrong_expected_hash_type() -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)

    with pytest.raises(
        TypeError,
        match="expected_hash must be an AuthenticationTokenHash",
    ):
        authentication_token_matches_hash(
            token=token,
            expected_hash=cast(Any, sha256(token.value.encode("ascii")).digest()),
        )


def test_authentication_token_matches_hash_uses_compare_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = RawAuthenticationToken(CANONICAL_TOKEN_VALUE)
    expected_hash = hash_authentication_token(token)
    compare_calls: list[tuple[bytes, bytes]] = []

    def fake_compare_digest(first: bytes, second: bytes) -> bool:
        compare_calls.append((first, second))
        return True

    monkeypatch.setattr(
        authentication_tokens_module,
        "compare_digest",
        fake_compare_digest,
    )

    result = authentication_token_matches_hash(
        token=token,
        expected_hash=expected_hash,
    )

    assert result is True
    assert len(compare_calls) == 1
    first_digest, second_digest = compare_calls[0]
    assert len(first_digest) == 32
    assert len(second_digest) == 32


def test_security_exports_public_symbols() -> None:
    from closeros import security

    assert security.RawAuthenticationToken is RawAuthenticationToken
    assert security.generate_raw_authentication_token is generate_raw_authentication_token
    assert security.hash_authentication_token is hash_authentication_token
    assert security.authentication_token_matches_hash is authentication_token_matches_hash


def test_private_constants_are_not_exported_from_security() -> None:
    from closeros import security

    assert "_TOKEN_ENTROPY_BYTES" not in security.__all__
    assert "_ENCODED_TOKEN_LENGTH" not in security.__all__
    assert "_URLSAFE_TOKEN_CHARACTERS" not in security.__all__
