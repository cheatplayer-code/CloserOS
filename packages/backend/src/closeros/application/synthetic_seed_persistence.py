"""Application persistence ports for synthetic seed provenance."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from closeros.domain.synthetic_seed import (
    SyntheticSeedManifest,
    SyntheticSeedResetState,
    SyntheticSeedResource,
)


class SyntheticSeedManifestRepository(Protocol):
    async def add(self, *, manifest: SyntheticSeedManifest) -> None: ...

    async def get_active_for_tenant(
        self,
        *,
        tenant_id: UUID,
        seed_version: str,
    ) -> SyntheticSeedManifest | None: ...

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> SyntheticSeedManifest | None: ...

    async def mark_reset_state(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
        reset_state: SyntheticSeedResetState,
        expected_state: SyntheticSeedResetState,
    ) -> SyntheticSeedManifest | None: ...


class SyntheticSeedResourceRepository(Protocol):
    async def add_many(self, *, resources: tuple[SyntheticSeedResource, ...]) -> None: ...

    async def list_for_manifest(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> tuple[SyntheticSeedResource, ...]: ...

    async def delete_for_manifest(
        self,
        *,
        tenant_id: UUID,
        manifest_id: UUID,
    ) -> int: ...


__all__ = [
    "SyntheticSeedManifestRepository",
    "SyntheticSeedResourceRepository",
]
