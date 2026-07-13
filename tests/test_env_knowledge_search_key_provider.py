"""Tests for env-backed knowledge search key provider."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

import pytest
from closeros.application.secret_ports import SecretResolver
from closeros.infrastructure.env_knowledge_search_key_provider import (
    EnvKnowledgeSearchKeyProvider,
    KnowledgeSearchKeyConfigurationError,
)

from tests.encryption_support import SERVICE_ID

_TENANT_A = UUID("00000000-0000-0000-0000-0000000000aa")
_TENANT_B = UUID("00000000-0000-0000-0000-0000000000bb")
_SECRET_REFERENCE = "env:KNOWLEDGE_SEARCH_KEY"
_THIRTY_TWO_BYTE_SECRET = "a" * 32


class _SyncSecretResolver(Protocol):
    def resolve_secret_sync(self, *, reference: str) -> bytes: ...


class _FixedSecretResolver:
    def __init__(self, *, secret: bytes) -> None:
        self._secret = secret

    def resolve_secret_sync(self, *, reference: str) -> bytes:
        if reference != _SECRET_REFERENCE:
            raise RuntimeError("unexpected secret reference")
        return self._secret


def _provider(*, version: str, resolver: _SyncSecretResolver) -> EnvKnowledgeSearchKeyProvider:
    return EnvKnowledgeSearchKeyProvider(
        secret_reference=_SECRET_REFERENCE,
        search_key_version=version,
        _secret_resolver=cast(SecretResolver, resolver),
    )


def test_env_knowledge_search_key_provider_tenant_digest_is_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_SEARCH_KEY", _THIRTY_TWO_BYTE_SECRET)
    provider = _provider(
        version="v-test-1",
        resolver=_FixedSecretResolver(secret=_THIRTY_TWO_BYTE_SECRET.encode("utf-8")),
    )
    first = provider.key_for_tenant(tenant_id=_TENANT_A)
    second = provider.key_for_tenant(tenant_id=_TENANT_A)
    other_tenant = provider.key_for_tenant(tenant_id=_TENANT_B)
    assert first == second
    assert first != other_tenant
    assert len(first) == 32


def test_env_knowledge_search_key_provider_changes_when_key_version_rotates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_SEARCH_KEY", _THIRTY_TWO_BYTE_SECRET)
    resolver = _FixedSecretResolver(secret=_THIRTY_TWO_BYTE_SECRET.encode("utf-8"))
    first = _provider(version="v-test-1", resolver=resolver)
    rotated = _provider(version="v-test-2", resolver=resolver)
    assert first.key_for_tenant(tenant_id=SERVICE_ID) != rotated.key_for_tenant(
        tenant_id=SERVICE_ID
    )


def test_env_knowledge_search_key_provider_repr_is_secret_free() -> None:
    provider = _provider(
        version="v-test-1",
        resolver=_FixedSecretResolver(secret=_THIRTY_TWO_BYTE_SECRET.encode("utf-8")),
    )
    rendered = repr(provider)
    assert "EnvKnowledgeSearchKeyProvider" in rendered
    assert "v-test-1" in rendered
    assert _THIRTY_TWO_BYTE_SECRET not in rendered
    assert _SECRET_REFERENCE not in rendered


def test_env_knowledge_search_key_provider_rejects_empty_reference() -> None:
    with pytest.raises(KnowledgeSearchKeyConfigurationError, match="secret_reference"):
        EnvKnowledgeSearchKeyProvider(secret_reference="   ")
