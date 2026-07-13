"""Tests for KMS key provider adapters."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from closeros.domain.encrypted_content import DATA_ENCRYPTION_KEY_SIZE_BYTES, GCM_NONCE_SIZE_BYTES
from closeros.infrastructure.remote_kms_key_provider import RemoteKmsKeyProvider
from closeros.infrastructure.static_key_provider import (
    ProductionStaticKeyProviderRejectedError,
    StaticKeyProvider,
    reject_static_key_provider_in_production,
)


def test_static_key_provider_rejected_in_production() -> None:
    provider = StaticKeyProvider(
        keys_by_version={"dev-kek-v1": b"\x01" * DATA_ENCRYPTION_KEY_SIZE_BYTES},
        active_version="dev-kek-v1",
    )
    with pytest.raises(ProductionStaticKeyProviderRejectedError):
        reject_static_key_provider_in_production(provider)


def test_remote_kms_key_provider_wrap_unwrap_roundtrip() -> None:
    tenant_id = uuid4()
    content_id = uuid4()
    data_key = b"\x02" * DATA_ENCRYPTION_KEY_SIZE_BYTES
    nonce = b"\x03" * GCM_NONCE_SIZE_BYTES
    observed_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers.append(dict(request.headers))
        payload = request.read().decode("utf-8")
        if request.url.path == "/v1/wrap":
            assert "plaintext" in payload
            assert "Authorization" in request.headers
            return httpx.Response(200, json={"result": data_key.hex()})
        if request.url.path == "/v1/unwrap":
            return httpx.Response(200, json={"result": data_key.hex()})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class _Resolver:
        def resolve_secret_sync(self, *, reference: str) -> bytes:
            assert reference == "env:KMS_TOKEN"
            return b"synthetic-kms-token"

    def client_factory() -> httpx.Client:
        return httpx.Client(
            transport=transport,
            base_url="https://kms.example",
            headers={"Authorization": "Bearer synthetic-kms-token"},
        )

    provider = RemoteKmsKeyProvider(
        base_url="https://kms.example",
        api_token_reference="env:KMS_TOKEN",
        active_key_version="kek-v1",
        key_versions=("kek-v1",),
        _token_resolver=_Resolver(),  # type: ignore[arg-type]
        _httpx_client_factory=client_factory,
    )
    wrapped = provider.wrap_data_key(
        tenant_id=tenant_id,
        content_id=content_id,
        aad_version=1,
        data_key=data_key,
        key_wrap_nonce=nonce,
    )
    unwrapped = provider.unwrap_data_key(
        tenant_id=tenant_id,
        content_id=content_id,
        aad_version=1,
        wrapped_data_key=wrapped,
        key_wrap_nonce=nonce,
        key_version="kek-v1",
    )
    assert unwrapped == data_key
    assert observed_headers
    assert "synthetic-kms-token" not in repr(provider)


def test_remote_kms_repr_hides_token() -> None:
    provider = RemoteKmsKeyProvider(
        base_url="https://kms.example",
        api_token_reference="env:KMS_TOKEN",
        active_key_version="kek-v1",
        key_versions=("kek-v1",),
    )
    rendered = repr(provider)
    assert "KMS_TOKEN" not in rendered
    assert "token" not in rendered.lower()


def test_remote_kms_requires_https() -> None:
    with pytest.raises(ValueError):
        RemoteKmsKeyProvider(
            base_url="http://kms.example",
            api_token_reference="env:KMS_TOKEN",
            active_key_version="kek-v1",
            key_versions=("kek-v1",),
        )
