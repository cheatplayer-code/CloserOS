"""Environment/secret-resolver-backed knowledge search key provider."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from uuid import UUID

from closeros.application.knowledge_search_key import (
    KEY_SIZE_BYTES,
    validate_knowledge_search_key,
)
from closeros.application.secret_ports import SecretResolver
from closeros.domain.knowledge import SEARCH_KEY_VERSION
from closeros.infrastructure.env_secret_resolver import EnvSecretResolver


class KnowledgeSearchKeyConfigurationError(RuntimeError):
    """Raised when production knowledge search key configuration is invalid."""


@dataclass(frozen=True, slots=True)
class EnvKnowledgeSearchKeyProvider:
    """Derives tenant-bound search keys from a secret resolved via SecretResolver."""

    secret_reference: str
    search_key_version: str = SEARCH_KEY_VERSION
    _secret_resolver: SecretResolver | None = field(default=None, repr=False, compare=False)
    _root_key: bytes = field(default=b"", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.secret_reference, str) or not self.secret_reference.strip():
            raise KnowledgeSearchKeyConfigurationError("secret_reference must not be empty")
        if type(self.search_key_version) is not str or not self.search_key_version.strip():
            raise KnowledgeSearchKeyConfigurationError("search_key_version must not be empty")
        resolver = self._secret_resolver or EnvSecretResolver()
        if not hasattr(resolver, "resolve_secret_sync"):
            raise KnowledgeSearchKeyConfigurationError(
                "secret resolver must support synchronous resolution"
            )
        raw = resolver.resolve_secret_sync(reference=self.secret_reference.strip())
        root = raw if len(raw) == KEY_SIZE_BYTES else hashlib.sha256(raw).digest()
        object.__setattr__(self, "_root_key", validate_knowledge_search_key(root))

    def __repr__(self) -> str:
        return f"EnvKnowledgeSearchKeyProvider(search_key_version={self.search_key_version!r})"

    def key_for_tenant(self, *, tenant_id: UUID) -> bytes:
        if not isinstance(tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        material = hmac.new(
            self._root_key,
            f"{self.search_key_version}:{tenant_id}".encode(),
            hashlib.sha256,
        ).digest()
        return validate_knowledge_search_key(material)


__all__ = [
    "EnvKnowledgeSearchKeyProvider",
    "KnowledgeSearchKeyConfigurationError",
]
