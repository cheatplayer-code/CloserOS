"""Remote KMS key provider using HTTPS wrap/unwrap behind KeyProvider."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse
from uuid import UUID

import httpx

from closeros.application.secret_ports import SecretResolutionError, SecretResolver
from closeros.domain.encrypted_content import (
    DATA_ENCRYPTION_KEY_SIZE_BYTES,
    ContentUnavailableError,
)
from closeros.infrastructure.aes_gcm_encryption import build_key_wrap_aad
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver

_MAX_RESPONSE_BYTES = 64 * 1024


class RemoteKmsError(Exception):
    """Base class for safe remote KMS failures."""


class RemoteKmsUnavailableError(RemoteKmsError):
    """Remote KMS is temporarily unavailable."""


class RemoteKmsUnauthorizedError(RemoteKmsError):
    """Remote KMS rejected credentials."""


class RemoteKmsMalformedResponseError(RemoteKmsError):
    """Remote KMS returned an invalid payload."""


class RemoteKmsUnknownKeyVersionError(RemoteKmsError):
    """Requested key version is not known to the remote KMS."""


def _validate_https_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if parsed.scheme != "https":
        raise ValueError("base_url must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not contain userinfo")
    if parsed.fragment:
        raise ValueError("base_url must not contain a fragment")
    if not parsed.hostname:
        raise ValueError("base_url must contain a hostname")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _map_http_status(status_code: int) -> RemoteKmsError:
    if status_code in {401, 403}:
        return RemoteKmsUnauthorizedError("remote kms unauthorized")
    if status_code == 404:
        return RemoteKmsUnknownKeyVersionError("remote kms key version unknown")
    if status_code >= 500:
        return RemoteKmsUnavailableError("remote kms is unavailable")
    return RemoteKmsMalformedResponseError("remote kms rejected request")


def _parse_result_hex(body: object) -> bytes:
    if not isinstance(body, dict):
        raise RemoteKmsMalformedResponseError("remote kms response is invalid")
    raw_result = body.get("result")
    if not isinstance(raw_result, str) or not raw_result:
        raise RemoteKmsMalformedResponseError("remote kms response is invalid")
    try:
        decoded = bytes.fromhex(raw_result)
    except ValueError as exc:
        raise RemoteKmsMalformedResponseError("remote kms response is invalid") from exc
    if len(decoded) != DATA_ENCRYPTION_KEY_SIZE_BYTES:
        raise RemoteKmsMalformedResponseError("remote kms key length is invalid")
    return decoded


@dataclass(frozen=True, slots=True)
class RemoteKmsKeyProvider:
    """Production KeyProvider adapter backed by a remote KMS HTTP API."""

    base_url: str
    api_token_reference: str
    active_key_version: str
    key_versions: tuple[str, ...]
    timeout_seconds: float = 10.0
    _token_resolver: SecretResolver | None = field(default=None, repr=False, compare=False)
    _httpx_client_factory: Callable[[], httpx.Client] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_https_base_url(self.base_url))
        if not isinstance(self.api_token_reference, str) or not self.api_token_reference.strip():
            raise ValueError("api_token_reference must not be empty")
        if not isinstance(self.active_key_version, str) or not self.active_key_version:
            raise ValueError("active_key_version must not be empty")
        if not self.key_versions:
            raise ValueError("key_versions must not be empty")
        if self.active_key_version not in self.key_versions:
            raise ValueError("active_key_version must be listed in key_versions")

    def __repr__(self) -> str:
        return (
            "RemoteKmsKeyProvider("
            f"active_key_version={self.active_key_version!r}, "
            f"versions={len(self.key_versions)}"
            ")"
        )

    def list_key_versions(self) -> tuple[str, ...]:
        return self.key_versions

    def wrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str | None = None,
    ) -> bytes:
        resolved_key_version = key_version or self.active_key_version
        if resolved_key_version not in self.key_versions:
            raise RemoteKmsUnknownKeyVersionError("remote kms key version unknown")
        associated_data = build_key_wrap_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            key_version=resolved_key_version,
            aad_version=aad_version,
        )
        return self._post_operation(
            path="/v1/wrap",
            payload={
                "key_version": resolved_key_version,
                "tenant_id": str(tenant_id),
                "content_id": str(content_id),
                "aad_version": aad_version,
                "aad": associated_data.hex(),
                "nonce": key_wrap_nonce.hex(),
                "plaintext": data_key.hex(),
            },
        )

    def unwrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        wrapped_data_key: bytes,
        key_wrap_nonce: bytes,
        key_version: str,
    ) -> bytes:
        if key_version not in self.key_versions:
            raise RemoteKmsUnknownKeyVersionError("remote kms key version unknown")
        associated_data = build_key_wrap_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            key_version=key_version,
            aad_version=aad_version,
        )
        return self._post_operation(
            path="/v1/unwrap",
            payload={
                "key_version": key_version,
                "tenant_id": str(tenant_id),
                "content_id": str(content_id),
                "aad_version": aad_version,
                "aad": associated_data.hex(),
                "nonce": key_wrap_nonce.hex(),
                "ciphertext": wrapped_data_key.hex(),
            },
        )

    def rewrap_data_key(
        self,
        *,
        tenant_id: UUID,
        content_id: UUID,
        aad_version: int,
        wrapped_data_key: bytes,
        key_wrap_nonce: bytes,
        source_key_version: str,
        target_key_version: str | None = None,
    ) -> bytes:
        resolved_target = target_key_version or self.active_key_version
        if source_key_version not in self.key_versions or resolved_target not in self.key_versions:
            raise RemoteKmsUnknownKeyVersionError("remote kms key version unknown")
        associated_data = build_key_wrap_aad(
            tenant_id=tenant_id,
            content_id=content_id,
            key_version=source_key_version,
            aad_version=aad_version,
        )
        return self._post_operation(
            path="/v1/rewrap",
            payload={
                "source_key_version": source_key_version,
                "target_key_version": resolved_target,
                "tenant_id": str(tenant_id),
                "content_id": str(content_id),
                "aad_version": aad_version,
                "aad": associated_data.hex(),
                "nonce": key_wrap_nonce.hex(),
                "ciphertext": wrapped_data_key.hex(),
            },
        )

    def _resolve_token(self) -> str:
        resolver = self._token_resolver or EnvSecretResolver()
        if hasattr(resolver, "resolve_secret_sync"):
            token_bytes = resolver.resolve_secret_sync(reference=self.api_token_reference)
        else:
            raise SecretResolutionError("token resolver does not support synchronous resolution")
        if not token_bytes:
            raise SecretResolutionError("kms api token is unavailable")
        return str(token_bytes.decode("utf-8"))

    def _open_client(self) -> httpx.Client:
        if self._httpx_client_factory is not None:
            return self._httpx_client_factory()
        token = self._resolve_token()
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _post_operation(self, *, path: str, payload: dict[str, object]) -> bytes:
        client = self._open_client()
        close_client = self._httpx_client_factory is None
        try:
            try:
                response = client.post(path, json=payload)
            except httpx.HTTPError as exc:
                raise RemoteKmsUnavailableError("remote kms request failed") from exc
            if len(response.content) > _MAX_RESPONSE_BYTES:
                raise RemoteKmsMalformedResponseError("remote kms response is too large")
            if response.status_code >= 400:
                mapped = _map_http_status(response.status_code)
                if isinstance(mapped, RemoteKmsUnavailableError):
                    raise ContentUnavailableError("remote kms is unavailable")
                if isinstance(mapped, RemoteKmsUnauthorizedError):
                    raise ContentUnavailableError("remote kms rejected request")
                raise ContentUnavailableError("remote kms response is invalid")
            return _parse_result_hex(response.json())
        finally:
            if close_client:
                client.close()


async def check_remote_kms_readiness(*, provider: RemoteKmsKeyProvider) -> bool:
    """Authenticated readiness probe for remote KMS connectivity."""
    client = provider._open_client()
    close_client = provider._httpx_client_factory is None
    try:
        try:
            response = client.get("/health")
        except httpx.HTTPError:
            return False
        if response.status_code in {401, 403}:
            return False
        return response.status_code == 200
    finally:
        if close_client:
            client.close()


__all__ = [
    "RemoteKmsError",
    "RemoteKmsKeyProvider",
    "RemoteKmsMalformedResponseError",
    "RemoteKmsUnauthorizedError",
    "RemoteKmsUnavailableError",
    "RemoteKmsUnknownKeyVersionError",
    "check_remote_kms_readiness",
]
