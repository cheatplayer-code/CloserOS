"""In-memory resolver for a deployment-injected AI provider credential."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from closeros.application.ai_ports import AiCredentialResolver
from closeros.domain.ai_analysis import AiProviderCode


@dataclass(frozen=True, slots=True)
class ConfiguredAiCredentialResolver(AiCredentialResolver):
    """Resolve one process-level bearer key without exposing it in repr output."""

    bearer_key: str = field(repr=False)
    provider_code: AiProviderCode = AiProviderCode.OPENAI_COMPATIBLE

    def __post_init__(self) -> None:
        if not isinstance(self.provider_code, AiProviderCode):
            raise TypeError("provider_code must be an AiProviderCode")
        if type(self.bearer_key) is not str:
            raise TypeError("bearer_key must be a string")
        normalized = self.bearer_key.strip()
        if not normalized:
            raise ValueError("bearer_key must not be empty")
        object.__setattr__(self, "bearer_key", normalized)

    async def resolve_bearer_key(
        self,
        *,
        tenant_id: UUID,
        provider_code: AiProviderCode,
    ) -> str | None:
        _ = tenant_id
        if provider_code is not self.provider_code:
            return None
        return self.bearer_key


__all__ = ["ConfiguredAiCredentialResolver"]
