"""Unit tests for encrypted-content domain validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    GCM_NONCE_SIZE_BYTES,
    PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES,
    RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES,
    ContentEncoding,
    ContentUnavailableError,
    DecryptedContent,
    EncryptedContent,
    EncryptedContentError,
    EncryptedContentKind,
    EncryptionAlgorithm,
    WrappedDataKey,
    max_plaintext_bytes_for_kind,
    validate_plaintext_for_kind,
)

from tests.encryption_support import NOW, SYNTHETIC_KEK_V1

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
CONTENT_ID = UUID("00000000-0000-0000-0000-00000000b001")
VALID_NONCE = bytes(GCM_NONCE_SIZE_BYTES)
EXPIRES = NOW + timedelta(days=30)


def _valid_wrapped_key() -> WrappedDataKey:
    return WrappedDataKey(
        wrapped_data_key=b"wrapped-key-bytes",
        key_wrap_nonce=VALID_NONCE,
        key_version="test-kek-v1",
    )


def _valid_encrypted_content(**overrides: object) -> EncryptedContent:
    defaults = {
        "id": CONTENT_ID,
        "tenant_id": TENANT_ID,
        "kind": EncryptedContentKind.RAW_MESSAGE,
        "encoding": ContentEncoding.UTF8,
        "ciphertext": b"ciphertext-bytes",
        "content_nonce": VALID_NONCE,
        "wrapped_data_key": b"wrapped-dek",
        "key_wrap_nonce": VALID_NONCE,
        "algorithm": EncryptionAlgorithm.AES_256_GCM,
        "key_version": "test-kek-v1",
        "aad_version": CONTENT_AAD_VERSION,
        "plaintext_byte_length": 12,
        "created_at": NOW,
        "expires_at": EXPIRES,
    }
    defaults.update(overrides)
    return EncryptedContent(**defaults)  # type: ignore[arg-type]


def test_wrapped_data_key_accepts_valid_values() -> None:
    wrapped = _valid_wrapped_key()
    assert wrapped.key_version == "test-kek-v1"
    assert len(wrapped.key_wrap_nonce) == GCM_NONCE_SIZE_BYTES


@pytest.mark.parametrize(
    ("field", "value", "error_match"),
    [
        ("wrapped_data_key", b"", "wrapped_data_key must not be empty"),
        ("key_wrap_nonce", b"short", "key_wrap_nonce must contain exactly"),
        ("key_version", "", "key_version must not be empty"),
        ("key_version", "bad key", "key_version must contain only letters"),
        ("key_version", "_bad", "key_version must start with a letter or digit"),
    ],
)
def test_wrapped_data_key_rejects_invalid_values(
    field: str,
    value: object,
    error_match: str,
) -> None:
    payload = {
        "wrapped_data_key": b"wrapped-key-bytes",
        "key_wrap_nonce": VALID_NONCE,
        "key_version": "test-kek-v1",
        field: value,
    }
    with pytest.raises(ValueError, match=error_match):
        WrappedDataKey(**payload)  # type: ignore[arg-type]


def test_encrypted_content_round_trip_fields() -> None:
    content = _valid_encrypted_content()
    assert content.kind is EncryptedContentKind.RAW_MESSAGE
    assert content.plaintext_byte_length == 12


@pytest.mark.parametrize(
    ("field", "value", "error_type", "error_match"),
    [
        ("content_nonce", b"short", ValueError, "content_nonce must contain exactly"),
        ("key_wrap_nonce", b"", ValueError, "key_wrap_nonce must contain exactly"),
        ("key_version", "!!!", ValueError, "key_version must contain only letters"),
        ("aad_version", 0, ValueError, "aad_version must be greater than or equal to one"),
        ("plaintext_byte_length", 0, ValueError, "plaintext_byte_length must be greater than zero"),
        (
            "plaintext_byte_length",
            RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES + 1,
            ValueError,
            "plaintext_byte_length exceeds allowed size limit",
        ),
        ("created_at", datetime(2026, 1, 1), ValueError, "created_at must be timezone-aware"),
        ("expires_at", NOW - timedelta(days=1), ValueError, "expires_at must not be earlier"),
    ],
)
def test_encrypted_content_rejects_invalid_values(
    field: str,
    value: object,
    error_type: type[Exception],
    error_match: str,
) -> None:
    overrides = {field: value}
    with pytest.raises(error_type, match=error_match):
        _valid_encrypted_content(**overrides)


def test_decrypted_content_as_utf8_text() -> None:
    decrypted = DecryptedContent(
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext_byte_length=5,
        _plaintext=b"hello",
    )
    assert decrypted.as_utf8_text() == "hello"


def test_decrypted_content_as_json_text() -> None:
    decrypted = DecryptedContent(
        kind=EncryptedContentKind.PROVIDER_PAYLOAD,
        encoding=ContentEncoding.JSON,
        plaintext_byte_length=2,
        _plaintext=b"{}",
    )
    assert decrypted.as_json_text() == "{}"


def test_decrypted_content_rejects_mismatched_length() -> None:
    with pytest.raises(ValueError, match="plaintext_byte_length must match plaintext size"):
        DecryptedContent(
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext_byte_length=10,
            _plaintext=b"short",
        )


def test_decrypted_content_rejects_wrong_encoding_access() -> None:
    decrypted = DecryptedContent(
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.BINARY,
        plaintext_byte_length=3,
        _plaintext=b"bin",
    )
    with pytest.raises(EncryptedContentError, match="encoding does not support utf8"):
        decrypted.as_utf8_text()


def test_max_plaintext_bytes_for_kind() -> None:
    assert max_plaintext_bytes_for_kind(EncryptedContentKind.RAW_MESSAGE) == (
        RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES
    )
    assert max_plaintext_bytes_for_kind(EncryptedContentKind.PROVIDER_PAYLOAD) == (
        PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES
    )


def test_validate_plaintext_for_kind_accepts_valid_payload() -> None:
    plaintext = b"synthetic payload"
    assert (
        validate_plaintext_for_kind(
            kind=EncryptedContentKind.RAW_MESSAGE,
            plaintext=plaintext,
        )
        == plaintext
    )


def test_validate_plaintext_for_kind_rejects_empty() -> None:
    with pytest.raises(EncryptedContentError, match="plaintext must not be empty"):
        validate_plaintext_for_kind(kind=EncryptedContentKind.RAW_MESSAGE, plaintext=b"")


def test_validate_plaintext_for_kind_rejects_oversized_raw_message() -> None:
    oversized = b"x" * (RAW_OR_SANITIZED_MAX_PLAINTEXT_BYTES + 1)
    with pytest.raises(EncryptedContentError, match="plaintext exceeds allowed size limit"):
        validate_plaintext_for_kind(kind=EncryptedContentKind.RAW_MESSAGE, plaintext=oversized)


def test_validate_plaintext_for_kind_rejects_oversized_provider_payload() -> None:
    oversized = b"x" * (PROVIDER_PAYLOAD_MAX_PLAINTEXT_BYTES + 1)
    with pytest.raises(EncryptedContentError, match="plaintext exceeds allowed size limit"):
        validate_plaintext_for_kind(
            kind=EncryptedContentKind.PROVIDER_PAYLOAD,
            plaintext=oversized,
        )


def test_max_plaintext_bytes_for_kind_rejects_invalid_kind() -> None:
    with pytest.raises(TypeError, match="kind must be an EncryptedContentKind"):
        max_plaintext_bytes_for_kind("raw_message")  # type: ignore[arg-type]


def test_encrypted_content_rejects_non_uuid_id() -> None:
    with pytest.raises(TypeError, match="id must be a UUID"):
        _valid_encrypted_content(id="not-a-uuid")


def test_wrapped_data_key_type_errors() -> None:
    with pytest.raises(TypeError, match="wrapped_data_key must be bytes"):
        WrappedDataKey(
            wrapped_data_key="not-bytes",  # type: ignore[arg-type]
            key_wrap_nonce=VALID_NONCE,
            key_version="test-kek-v1",
        )


def test_decrypted_content_rejects_invalid_utf8() -> None:
    decrypted = DecryptedContent(
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext_byte_length=2,
        _plaintext=b"\xff\xfe",
    )
    with pytest.raises(EncryptedContentError, match="plaintext is not valid utf8"):
        decrypted.as_utf8_text()


def test_content_unavailable_error_is_encrypted_content_error() -> None:
    assert issubclass(ContentUnavailableError, EncryptedContentError)


def test_encrypted_content_repr_hides_sensitive_bytes() -> None:
    content = _valid_encrypted_content()
    rendered = repr(content)
    assert "ciphertext-bytes" not in rendered
    assert str(CONTENT_ID) in rendered


def test_wrapped_key_does_not_expose_key_material_in_repr() -> None:
    wrapped = _valid_wrapped_key()
    assert SYNTHETIC_KEK_V1.decode("latin-1") not in repr(wrapped)
