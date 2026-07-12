"""Unit tests for tenant-scoped knowledge retrieval service."""

# mypy: disable-error-code=unused-ignore

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from closeros.application.audit_recording import AuditContext
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.application.knowledge_persistence import KnowledgeLexicalMatch
from closeros.application.knowledge_retrieval import (
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalService,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import ContentEncoding, EncryptedContentKind
from closeros.domain.knowledge import KnowledgeDocumentKind

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class _Decrypted:
    kind: EncryptedContentKind
    encoding: ContentEncoding
    text: str

    def as_utf8_text(self) -> str:
        return self.text


class _KnowledgeTermsRepo:
    def __init__(self, matches: tuple[KnowledgeLexicalMatch, ...]) -> None:
        self._matches = matches

    async def search_ranked(self, **_: object) -> tuple[KnowledgeLexicalMatch, ...]:
        return self._matches


class _AuditRepo:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def append(self, event: object) -> None:
        self.events.append(event)


class _Uow:
    def __init__(
        self, *, matches: tuple[KnowledgeLexicalMatch, ...], audit_repo: _AuditRepo
    ) -> None:
        self.knowledge_chunk_terms = _KnowledgeTermsRepo(matches)
        self.audit_events = audit_repo

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def commit(self) -> None:
        return None


class _Encryption:
    def __init__(self, decrypted: _Decrypted) -> None:
        self._decrypted = decrypted
        self.calls = 0

    async def load_and_decrypt(self, **_: object) -> _Decrypted:
        self.calls += 1
        return self._decrypted


def _encryption(decrypted: _Decrypted) -> ContentEncryptionService:
    return cast(ContentEncryptionService, _Encryption(decrypted))


def _match() -> KnowledgeLexicalMatch:
    return KnowledgeLexicalMatch(
        chunk_id=UUID("00000000-0000-0000-0000-000000000101"),
        content_id=UUID("00000000-0000-0000-0000-000000000102"),
        document_id=UUID("00000000-0000-0000-0000-000000000103"),
        document_version_id=UUID("00000000-0000-0000-0000-000000000104"),
        source_code="kb_sales_playbook",
        version_number=1,
        document_kind=KnowledgeDocumentKind.GENERAL_REFERENCE,
        match_weight=9000,
        matched_term_count=3,
        chunk_position=0,
    )


def _uow_factory(
    *,
    matches: tuple[KnowledgeLexicalMatch, ...],
    audit_repo: _AuditRepo,
) -> IntegratedUnitOfWork:
    return cast(IntegratedUnitOfWork, _Uow(matches=matches, audit_repo=audit_repo))


def _request(query_text: str) -> KnowledgeRetrievalRequest:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    return KnowledgeRetrievalRequest(
        tenant_id=TENANT_ID,
        query_text=query_text,
        analysis_target_id=UUID("00000000-0000-0000-0000-000000000201"),
        occurred_at=now,
        audit_context=AuditContext(correlation_id=UUID("00000000-0000-0000-0000-000000000202")),
        actor_type=AuditActorType.SERVICE,
        actor_id=UUID("00000000-0000-0000-0000-000000000203"),
        limit=8,
    )


def test_retrieve_returns_empty_for_blank_query() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=object(),  # type: ignore[arg-type]
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.KNOWLEDGE_CHUNK, ContentEncoding.UTF8, "x")
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000301"),
        )
        assert await service.retrieve(_request("   ")) == ()
        assert not audit_repo.events

    asyncio.run(exercise())


def test_retrieve_returns_ranked_decrypted_results_and_appends_audit() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        encryption_impl = _Encryption(
            _Decrypted(
                EncryptedContentKind.KNOWLEDGE_CHUNK,
                ContentEncoding.UTF8,
                "Synthetic policy snippet.",
            )
        )
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=cast(ContentEncryptionService, encryption_impl),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000302"),
        )
        results = await service.retrieve(_request("pricing timeline"))
        assert len(results) == 1
        assert results[0].decrypted_text == "Synthetic policy snippet."
        assert encryption_impl.calls == 1
        assert len(audit_repo.events) == 1

    asyncio.run(exercise())


def test_retrieve_skips_non_knowledge_chunk_content_kind() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.SANITIZED_MESSAGE, ContentEncoding.UTF8, "x")
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000303"),
        )
        results = await service.retrieve(_request("pricing timeline"))
        assert results == ()
        assert not audit_repo.events

    asyncio.run(exercise())


def test_retrieve_skips_non_utf8_knowledge_chunk_encoding() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.KNOWLEDGE_CHUNK, ContentEncoding.JSON, '{"x":1}')
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000304"),
        )
        results = await service.retrieve(_request("pricing timeline"))
        assert results == ()
        assert not audit_repo.events

    asyncio.run(exercise())


def test_retrieve_rejects_non_positive_limit() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.KNOWLEDGE_CHUNK, ContentEncoding.UTF8, "x")
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000305"),
        )
        request = _request("pricing timeline")
        request = KnowledgeRetrievalRequest(
            tenant_id=request.tenant_id,
            query_text=request.query_text,
            analysis_target_id=request.analysis_target_id,
            occurred_at=request.occurred_at,
            audit_context=request.audit_context,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            limit=0,
        )
        with pytest.raises(ValueError, match="positive"):
            await service.retrieve(request)

    asyncio.run(exercise())


def test_retrieve_returns_empty_when_ranked_search_has_no_matches() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.KNOWLEDGE_CHUNK, ContentEncoding.UTF8, "x")
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000306"),
        )
        results = await service.retrieve(_request("pricing timeline"))
        assert results == ()
        assert not audit_repo.events

    asyncio.run(exercise())


def test_retrieve_returns_empty_when_query_has_only_stop_words() -> None:
    async def exercise() -> None:
        audit_repo = _AuditRepo()
        service = KnowledgeRetrievalService(
            uow_factory=lambda: _uow_factory(matches=(_match(),), audit_repo=audit_repo),
            key_provider=type(
                "KeyProvider", (), {"key_for_tenant": lambda self, tenant_id: bytes(range(32))}
            )(),
            content_encryption=_encryption(
                _Decrypted(EncryptedContentKind.KNOWLEDGE_CHUNK, ContentEncoding.UTF8, "x")
            ),
            uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000307"),
        )
        results = await service.retrieve(_request("the and for in"))
        assert results == ()
        assert not audit_repo.events

    asyncio.run(exercise())
