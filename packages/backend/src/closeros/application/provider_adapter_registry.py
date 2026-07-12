"""Explicit provider adapter registry."""

from __future__ import annotations

from closeros.application.provider_ports import ProviderAdapterError, ProviderWebhookAdapter
from closeros.domain.canonical_enums import ProviderKind


class ProviderAdapterRegistryError(ProviderAdapterError):
    """Base class for registry failures."""


class DuplicateProviderAdapterError(ProviderAdapterRegistryError):
    """Raised when a provider adapter is registered twice."""


class UnknownProviderAdapterError(ProviderAdapterRegistryError):
    """Raised when no adapter is registered for a provider kind."""


class ProviderAdapterRegistry:
    """Maps controlled provider kinds to explicitly injected adapters."""

    def __init__(self, *, adapters: tuple[ProviderWebhookAdapter, ...] = ()) -> None:
        self._adapters: dict[ProviderKind, ProviderWebhookAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ProviderWebhookAdapter) -> None:
        if not hasattr(adapter, "provider_kind"):
            raise TypeError("adapter must expose provider_kind")

        provider_kind = adapter.provider_kind
        if not isinstance(provider_kind, ProviderKind):
            raise TypeError("provider_kind must be a ProviderKind")

        if provider_kind in self._adapters:
            raise DuplicateProviderAdapterError("provider adapter already registered")

        self._adapters[provider_kind] = adapter

    def resolve(self, provider_kind: ProviderKind) -> ProviderWebhookAdapter:
        if not isinstance(provider_kind, ProviderKind):
            raise TypeError("provider_kind must be a ProviderKind")

        adapter = self._adapters.get(provider_kind)
        if adapter is None:
            raise UnknownProviderAdapterError("provider adapter unavailable")

        return adapter

    def registered_kinds(self) -> frozenset[ProviderKind]:
        return frozenset(self._adapters)
