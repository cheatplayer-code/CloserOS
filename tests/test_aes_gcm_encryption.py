"""Unit tests for AES-256-GCM content cryptography."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from closeros.domain.encrypted_content import (
    CONTENT_AAD_VERSION,
    ContentEncoding,
    ContentUnavailableError,
    EncryptedContentKind,
)
from closeros.infrastructure.aes_gcm_encryption import (
    build_content_aad,
    build_key_wrap_aad,
)

from tests.encryption_support import (
    CONTENT_B_ID,
    CONTENT_ID,
    LATER,
    NOW,
    SYNTHETIC_PLAINTEXT_JSON,
    SYNTHETIC_PLAINTEXT_UTF8,
    TEST_KEY_VERSION_V1,
    TEST_KEY_VERSION_V2,
    DeterministicSecureRandom,
    build_test_cryptography,
    build_test_key_provider,
)

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
TENANT_B = UUID("00000000-0000-0000-0000-000000000002")


def test_build_content_aad_is_deterministic() -> None:
    first = build_content_aad(
        tenant_id=TENANT_A,
        content_id=CONTENT_ID,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        aad_version=CONTENT_AAD_VERSION,
    )
    second = build_content_aad(
        tenant_id=TENANT_A,
        content_id=CONTENT_ID,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        aad_version=CONTENT_AAD_VERSION,
    )
    assert first == second
    assert TENANT_B.bytes not in first


def test_build_key_wrap_aad_includes_key_version() -> None:
    aad = build_key_wrap_aad(
        tenant_id=TENANT_A,
        content_id=CONTENT_ID,
        key_version=TEST_KEY_VERSION_V1,
        aad_version=CONTENT_AAD_VERSION,
    )
    assert TEST_KEY_VERSION_V1.encode() in aad


def test_encrypt_decrypt_round_trip_utf8() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    decrypted = crypto.decrypt_content(encrypted=encrypted)
    assert decrypted.as_utf8_text() == SYNTHETIC_PLAINTEXT_UTF8.decode("utf-8")
    assert decrypted.plaintext_byte_length == len(SYNTHETIC_PLAINTEXT_UTF8)


def test_encrypt_decrypt_round_trip_json_provider_payload() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.PROVIDER_PAYLOAD,
        encoding=ContentEncoding.JSON,
        plaintext=SYNTHETIC_PLAINTEXT_JSON,
        created_at=NOW,
        expires_at=LATER,
    )
    decrypted = crypto.decrypt_content(encrypted=encrypted)
    assert decrypted.as_json_text() == SYNTHETIC_PLAINTEXT_JSON.decode("utf-8")


def test_tampered_ciphertext_fails_closed() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    tampered = replace(encrypted, ciphertext=encrypted.ciphertext[:-1] + b"\x00")
    with pytest.raises(ContentUnavailableError, match="encrypted content is unavailable"):
        crypto.decrypt_content(encrypted=tampered)


def test_tampered_content_nonce_fails_closed() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    tampered_nonce = bytes(b ^ 0xFF for b in encrypted.content_nonce)
    tampered = replace(encrypted, content_nonce=tampered_nonce)
    with pytest.raises(ContentUnavailableError):
        crypto.decrypt_content(encrypted=tampered)


def test_cross_tenant_aad_mismatch_fails_decrypt() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    cross_tenant = replace(encrypted, tenant_id=TENANT_B)
    with pytest.raises(ContentUnavailableError):
        crypto.decrypt_content(encrypted=cross_tenant)


def test_rewrap_data_key_produces_new_wrap_material() -> None:
    crypto = build_test_cryptography(
        secure_random=DeterministicSecureRandom(seed_bytes=bytes(range(256))),
    )
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    rewrapped = crypto.rewrap_data_key(encrypted=encrypted)
    assert rewrapped.wrapped_data_key != encrypted.wrapped_data_key
    assert rewrapped.key_version == TEST_KEY_VERSION_V1


def test_rewrap_with_rotated_active_key_version() -> None:
    provider_v1 = build_test_key_provider(active_version=TEST_KEY_VERSION_V1)
    crypto_v1 = build_test_cryptography(key_provider=provider_v1)
    encrypted = crypto_v1.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    assert encrypted.key_version == TEST_KEY_VERSION_V1

    provider_v2 = build_test_key_provider(active_version=TEST_KEY_VERSION_V2)
    crypto_v2 = build_test_cryptography(key_provider=provider_v2)
    rewrapped = crypto_v2.rewrap_data_key(encrypted=encrypted)
    assert rewrapped.key_version == TEST_KEY_VERSION_V2

    updated = replace(
        encrypted,
        wrapped_data_key=rewrapped.wrapped_data_key,
        key_wrap_nonce=rewrapped.key_wrap_nonce,
        key_version=rewrapped.key_version,
    )
    decrypted = crypto_v2.decrypt_content(encrypted=updated)
    assert decrypted.as_utf8_text() == SYNTHETIC_PLAINTEXT_UTF8.decode("utf-8")


def test_unknown_key_version_fails_unwrap() -> None:
    crypto = build_test_cryptography()
    encrypted = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    unknown_version = replace(encrypted, key_version="missing-version")
    with pytest.raises(ContentUnavailableError):
        crypto.decrypt_content(encrypted=unknown_version)


def test_decrypt_rejects_non_encrypted_content_type() -> None:
    crypto = build_test_cryptography()
    with pytest.raises(TypeError, match="encrypted must be an EncryptedContent"):
        crypto.decrypt_content(encrypted=object())  # type: ignore[arg-type]


def test_encrypt_rejects_empty_plaintext() -> None:
    crypto = build_test_cryptography()
    with pytest.raises(Exception, match="plaintext must not be empty"):
        crypto.encrypt_plaintext(
            content_id=uuid4(),
            tenant_id=TENANT_A,
            kind=EncryptedContentKind.RAW_MESSAGE,
            encoding=ContentEncoding.UTF8,
            plaintext=b"",
            created_at=NOW,
            expires_at=LATER,
        )


def test_aes_gcm_cryptography_repr_hides_secrets() -> None:
    crypto = build_test_cryptography()
    assert "StaticKeyProvider" not in repr(crypto)
    assert SYNTHETIC_PLAINTEXT_UTF8.decode() not in repr(crypto)


def test_different_content_ids_produce_different_ciphertext() -> None:
    crypto = build_test_cryptography(
        secure_random=DeterministicSecureRandom(seed_bytes=bytes(128)),
    )
    first = crypto.encrypt_plaintext(
        content_id=CONTENT_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    second = crypto.encrypt_plaintext(
        content_id=CONTENT_B_ID,
        tenant_id=TENANT_A,
        kind=EncryptedContentKind.RAW_MESSAGE,
        encoding=ContentEncoding.UTF8,
        plaintext=SYNTHETIC_PLAINTEXT_UTF8,
        created_at=NOW,
        expires_at=LATER,
    )
    assert first.ciphertext != second.ciphertext
