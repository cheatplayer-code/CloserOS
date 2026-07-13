"""Knowledge lexical-search key provider ports and development adapter."""

from __future__ import annotations

import hashlib
import os
from typing import Protocol
from uuid import UUID

from closeros.domain.knowledge import SEARCH_KEY_VERSION

KEY_SIZE_BYTES = 32
_KEY_SIZE_BYTES = KEY_SIZE_BYTES
_DEV_ENV_KEY_HEX = "CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX"
_DEV_FALLBACK_SEED = b"closeros-dev-knowledge-search-key-v1"


def validate_knowledge_search_key(key: bytes) -> bytes:
    if type(key) is not bytes:
        raise TypeError("knowledge search key must be bytes")
    if len(key) != _KEY_SIZE_BYTES:
        raise ValueError("knowledge search key must contain exactly 32 bytes")
    return key


class KnowledgeSearchKeyProvider(Protocol):
    @property
    def search_key_version(self) -> str: ...

    def key_for_tenant(self, *, tenant_id: UUID) -> bytes: ...


class DevKnowledgeSearchKeyProvider:
    """Development-only fixed key provider for deterministic lexical indexing."""

    def __init__(
        self,
        *,
        search_key_version: str = SEARCH_KEY_VERSION,
        key: bytes | None = None,
    ) -> None:
        if type(search_key_version) is not str or not search_key_version.strip():
            raise ValueError("search_key_version must be a non-empty string")
        self._search_key_version = search_key_version
        self._key = validate_knowledge_search_key(
            key if key is not None else self._load_or_generate_key()
        )

    @property
    def search_key_version(self) -> str:
        return self._search_key_version

    def key_for_tenant(self, *, tenant_id: UUID) -> bytes:
        if not isinstance(tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        return self._key

    def _load_or_generate_key(self) -> bytes:
        raw_hex = os.environ.get(_DEV_ENV_KEY_HEX, "").strip()
        if raw_hex:
            try:
                return validate_knowledge_search_key(bytes.fromhex(raw_hex))
            except ValueError as error:
                raise ValueError(f"{_DEV_ENV_KEY_HEX} must be a 64-char hex string") from error
        return hashlib.sha256(_DEV_FALLBACK_SEED).digest()
