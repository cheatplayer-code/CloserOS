"""Configured fixed-key provider for non-development lexical search runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from closeros.application.knowledge_search_key import validate_knowledge_search_key


@dataclass(frozen=True, slots=True)
class ConfiguredKnowledgeSearchKeyProvider:
    """Provide one deployment-injected 32-byte search key without exposing it."""

    search_key_version: str
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        version = self.search_key_version.strip()
        if not version:
            raise ValueError("search_key_version must be a non-empty string")
        object.__setattr__(self, "search_key_version", version)
        object.__setattr__(self, "key", validate_knowledge_search_key(self.key))

    def key_for_tenant(self, *, tenant_id: UUID) -> bytes:
        if not isinstance(tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        return self.key


__all__ = ["ConfiguredKnowledgeSearchKeyProvider"]
