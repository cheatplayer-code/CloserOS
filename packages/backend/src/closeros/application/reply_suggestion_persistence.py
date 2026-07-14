"""Persistence ports for reply suggestions and buyer memory."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from closeros.domain.buyer_memory import BuyerMemoryFact
from closeros.domain.reply_suggestion import (
    ReplySuggestionCandidate,
    ReplySuggestionEvent,
    ReplySuggestionRun,
)


class ReplySuggestionRunRepository(Protocol):
    async def get(self, *, tenant_id: UUID, run_id: UUID) -> ReplySuggestionRun | None: ...

    async def get_by_idempotency(
        self, *, tenant_id: UUID, idempotency_key: str
    ) -> ReplySuggestionRun | None: ...

    async def latest_for_thread(
        self, *, tenant_id: UUID, conversation_thread_id: UUID
    ) -> ReplySuggestionRun | None: ...

    async def save(self, run: ReplySuggestionRun) -> ReplySuggestionRun: ...


class ReplySuggestionCandidateRepository(Protocol):
    async def list_for_run(
        self, *, tenant_id: UUID, run_id: UUID
    ) -> Sequence[ReplySuggestionCandidate]: ...

    async def get(
        self, *, tenant_id: UUID, candidate_id: UUID
    ) -> ReplySuggestionCandidate | None: ...

    async def replace_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        candidates: Sequence[ReplySuggestionCandidate],
    ) -> None: ...


class ReplySuggestionEventRepository(Protocol):
    async def append(self, event: ReplySuggestionEvent) -> ReplySuggestionEvent: ...

    async def list_for_run(
        self, *, tenant_id: UUID, run_id: UUID
    ) -> Sequence[ReplySuggestionEvent]: ...


class BuyerMemoryFactRepository(Protocol):
    async def get(self, *, tenant_id: UUID, fact_id: UUID) -> BuyerMemoryFact | None: ...

    async def list_for_thread(
        self, *, tenant_id: UUID, conversation_thread_id: UUID
    ) -> Sequence[BuyerMemoryFact]: ...

    async def list_for_lead(
        self, *, tenant_id: UUID, lead_id: UUID
    ) -> Sequence[BuyerMemoryFact]: ...

    async def save(self, fact: BuyerMemoryFact) -> BuyerMemoryFact: ...
