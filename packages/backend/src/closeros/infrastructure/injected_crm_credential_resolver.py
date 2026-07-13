"""Deterministic injected CRM credential resolver for tests."""

from __future__ import annotations

from uuid import UUID

from closeros.domain.provider_credentials import SecretBytes


class InjectedCrmCredentialResolver:
    def __init__(self, *, secrets_by_reference: dict[str, bytes]) -> None:
        self._secrets_by_reference = {
            key: SecretBytes(value=value)
            for key, value in secrets_by_reference.items()
            if type(value) is bytes and value
        }

    async def resolve_access_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = crm_connection_id
        return self._secrets_by_reference.get(reference_key)

    async def resolve_refresh_token(
        self,
        *,
        tenant_id: UUID,
        crm_connection_id: UUID,
        reference_key: str,
    ) -> SecretBytes | None:
        _ = tenant_id
        _ = crm_connection_id
        return self._secrets_by_reference.get(reference_key)


__all__ = ["InjectedCrmCredentialResolver"]
