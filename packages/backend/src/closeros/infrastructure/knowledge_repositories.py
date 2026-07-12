"""PostgreSQL repository implementations for knowledge persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.knowledge_persistence import (
    DuplicateKnowledgeChunkError,
    DuplicateKnowledgeDocumentError,
    DuplicateKnowledgeDocumentVersionError,
    KnowledgeChunkRecord,
    KnowledgeChunkTermRecord,
    KnowledgeDocumentRecord,
    KnowledgeDocumentVersionNotFoundError,
    KnowledgeDocumentVersionRecord,
    KnowledgeLexicalMatch,
    KnowledgePersistenceError,
)
from closeros.domain.knowledge import KnowledgeDocumentKind
from closeros.infrastructure import knowledge_mappers as mappers
from closeros.infrastructure.knowledge_orm import (
    KnowledgeChunkRow,
    KnowledgeChunkTermRow,
    KnowledgeDocumentRow,
    KnowledgeDocumentVersionRow,
)
from closeros.infrastructure.persistence_errors import translate_integrity_error
from closeros.infrastructure.repository_helpers import tenant_scoped_get

_CONSTRAINT_ERRORS: dict[str, type[KnowledgePersistenceError]] = {
    "pk_knowledge_documents": DuplicateKnowledgeDocumentError,
    "uq_knowledge_documents_tenant_id_id": DuplicateKnowledgeDocumentError,
    "pk_knowledge_document_versions": DuplicateKnowledgeDocumentVersionError,
    "uq_knowledge_document_versions_tenant_id_id": DuplicateKnowledgeDocumentVersionError,
    "uq_knowledge_document_versions_tenant_document_id_version_number": (
        DuplicateKnowledgeDocumentVersionError
    ),
    "pk_knowledge_chunks": DuplicateKnowledgeChunkError,
    "uq_knowledge_chunks_tenant_id_id": DuplicateKnowledgeChunkError,
    "uq_knowledge_chunks_tenant_document_version_id_position": DuplicateKnowledgeChunkError,
}


def _translate_integrity_error(error: IntegrityError) -> KnowledgePersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=KnowledgePersistenceError,
        message="knowledge persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyKnowledgeDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: KnowledgeDocumentRecord) -> None:
        self._session.add(mappers.document_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord | None:
        row = await tenant_scoped_get(
            self._session,
            KnowledgeDocumentRow,
            tenant_id=tenant_id,
            record_id=document_id,
        )
        return None if row is None else mappers.document_to_record(row)

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[KnowledgeDocumentRecord, ...]:
        statement = (
            select(KnowledgeDocumentRow)
            .where(KnowledgeDocumentRow.tenant_id == tenant_id)
            .order_by(KnowledgeDocumentRow.updated_at.desc(), KnowledgeDocumentRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.document_to_record(row) for row in rows)


class SqlAlchemyKnowledgeDocumentVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: KnowledgeDocumentVersionRecord) -> None:
        self._session.add(mappers.version_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
    ) -> KnowledgeDocumentVersionRecord | None:
        row = await tenant_scoped_get(
            self._session,
            KnowledgeDocumentVersionRow,
            tenant_id=tenant_id,
            record_id=version_id,
        )
        return None if row is None else mappers.version_to_record(row)

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
    ) -> KnowledgeDocumentVersionRecord | None:
        statement = (
            select(KnowledgeDocumentVersionRow)
            .where(
                KnowledgeDocumentVersionRow.tenant_id == tenant_id,
                KnowledgeDocumentVersionRow.id == version_id,
            )
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else mappers.version_to_record(row)

    async def list_by_document(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        limit: int = 50,
    ) -> tuple[KnowledgeDocumentVersionRecord, ...]:
        statement = (
            select(KnowledgeDocumentVersionRow)
            .where(
                KnowledgeDocumentVersionRow.tenant_id == tenant_id,
                KnowledgeDocumentVersionRow.document_id == document_id,
            )
            .order_by(
                KnowledgeDocumentVersionRow.version_number.desc(),
                KnowledgeDocumentVersionRow.created_at.desc(),
            )
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.version_to_record(row) for row in rows)

    async def allocate_next_version_number(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> int:
        statement = select(func.max(KnowledgeDocumentVersionRow.version_number)).where(
            KnowledgeDocumentVersionRow.tenant_id == tenant_id,
            KnowledgeDocumentVersionRow.document_id == document_id,
        )
        max_version = (await self._session.execute(statement)).scalar_one_or_none()
        return int(max_version or 0) + 1

    async def mark_approved(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        approved_at: datetime,
    ) -> KnowledgeDocumentVersionRecord:
        statement = (
            update(KnowledgeDocumentVersionRow)
            .where(
                KnowledgeDocumentVersionRow.tenant_id == tenant_id,
                KnowledgeDocumentVersionRow.id == version_id,
            )
            .values(status="approved", approved_at=approved_at)
            .returning(KnowledgeDocumentVersionRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise KnowledgeDocumentVersionNotFoundError("knowledge version not found")
        await _flush(self._session)
        return mappers.version_to_record(row)

    async def mark_indexed(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        indexed_at: datetime,
    ) -> KnowledgeDocumentVersionRecord:
        statement = (
            update(KnowledgeDocumentVersionRow)
            .where(
                KnowledgeDocumentVersionRow.tenant_id == tenant_id,
                KnowledgeDocumentVersionRow.id == version_id,
            )
            .values(status="indexed", indexed_at=indexed_at)
            .returning(KnowledgeDocumentVersionRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise KnowledgeDocumentVersionNotFoundError("knowledge version not found")
        await _flush(self._session)
        return mappers.version_to_record(row)

    async def mark_revoked(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        revoked_at: datetime,
    ) -> KnowledgeDocumentVersionRecord:
        statement = (
            update(KnowledgeDocumentVersionRow)
            .where(
                KnowledgeDocumentVersionRow.tenant_id == tenant_id,
                KnowledgeDocumentVersionRow.id == version_id,
            )
            .values(status="revoked", revoked_at=revoked_at)
            .returning(KnowledgeDocumentVersionRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            raise KnowledgeDocumentVersionNotFoundError("knowledge version not found")
        await _flush(self._session)
        return mappers.version_to_record(row)


class SqlAlchemyKnowledgeChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self,
        *,
        chunks: tuple[KnowledgeChunkRecord, ...],
    ) -> None:
        for record in chunks:
            self._session.add(mappers.chunk_to_row(record))
        if chunks:
            await _flush(self._session)

    async def list_by_document_version(
        self,
        *,
        tenant_id: UUID,
        document_version_id: UUID,
    ) -> tuple[KnowledgeChunkRecord, ...]:
        statement = (
            select(KnowledgeChunkRow)
            .where(
                KnowledgeChunkRow.tenant_id == tenant_id,
                KnowledgeChunkRow.document_version_id == document_version_id,
            )
            .order_by(KnowledgeChunkRow.position.asc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.chunk_to_record(row) for row in rows)

    async def revoke_by_document_version(
        self,
        *,
        tenant_id: UUID,
        document_version_id: UUID,
    ) -> int:
        statement = (
            update(KnowledgeChunkRow)
            .where(
                KnowledgeChunkRow.tenant_id == tenant_id,
                KnowledgeChunkRow.document_version_id == document_version_id,
                KnowledgeChunkRow.status != "revoked",
            )
            .values(status="revoked")
            .returning(KnowledgeChunkRow.id)
        )
        result = await self._session.execute(statement)
        revoked_ids = result.scalars().all()
        await _flush(self._session)
        return len(revoked_ids)


class SqlAlchemyKnowledgeChunkTermRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_chunk(
        self,
        *,
        tenant_id: UUID,
        chunk_id: UUID,
        terms: tuple[KnowledgeChunkTermRecord, ...],
    ) -> None:
        delete_statement = delete(KnowledgeChunkTermRow).where(
            KnowledgeChunkTermRow.tenant_id == tenant_id,
            KnowledgeChunkTermRow.chunk_id == chunk_id,
        )
        await self._session.execute(delete_statement)
        for term in terms:
            self._session.add(mappers.chunk_term_to_row(term))
        await _flush(self._session)

    async def search_ranked(
        self,
        *,
        tenant_id: UUID,
        term_digests: tuple[bytes, ...],
        limit: int,
    ) -> tuple[KnowledgeLexicalMatch, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not term_digests:
            return ()

        match_weight = func.sum(KnowledgeChunkTermRow.weight_basis_points).label("match_weight")
        matched_term_count = func.count(KnowledgeChunkTermRow.term_digest).label(
            "matched_term_count"
        )
        statement = (
            select(
                KnowledgeChunkRow.id.label("chunk_id"),
                KnowledgeChunkRow.content_id.label("content_id"),
                KnowledgeChunkRow.document_version_id.label("document_version_id"),
                KnowledgeChunkRow.position.label("chunk_position"),
                KnowledgeDocumentVersionRow.document_id.label("document_id"),
                KnowledgeDocumentVersionRow.version_number.label("version_number"),
                KnowledgeDocumentRow.external_reference.label("external_reference"),
                match_weight,
                matched_term_count,
            )
            .join(
                KnowledgeChunkRow,
                (KnowledgeChunkRow.id == KnowledgeChunkTermRow.chunk_id)
                & (KnowledgeChunkRow.tenant_id == KnowledgeChunkTermRow.tenant_id),
            )
            .join(
                KnowledgeDocumentVersionRow,
                (KnowledgeDocumentVersionRow.id == KnowledgeChunkRow.document_version_id)
                & (KnowledgeDocumentVersionRow.tenant_id == KnowledgeChunkRow.tenant_id),
            )
            .join(
                KnowledgeDocumentRow,
                (KnowledgeDocumentRow.id == KnowledgeDocumentVersionRow.document_id)
                & (KnowledgeDocumentRow.tenant_id == KnowledgeDocumentVersionRow.tenant_id),
            )
            .where(
                KnowledgeChunkTermRow.tenant_id == tenant_id,
                KnowledgeChunkRow.status == "active",
                KnowledgeDocumentVersionRow.status == "indexed",
                KnowledgeDocumentRow.status == "active",
                KnowledgeChunkTermRow.term_digest.in_(term_digests),
            )
            .group_by(
                KnowledgeChunkRow.id,
                KnowledgeChunkRow.content_id,
                KnowledgeChunkRow.document_version_id,
                KnowledgeChunkRow.position,
                KnowledgeDocumentVersionRow.document_id,
                KnowledgeDocumentVersionRow.version_number,
                KnowledgeDocumentRow.external_reference,
            )
            .order_by(
                match_weight.desc(), matched_term_count.desc(), KnowledgeChunkRow.position.asc()
            )
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        result: list[KnowledgeLexicalMatch] = []
        for row in rows:
            source_code = row.external_reference or "upload"
            result.append(
                KnowledgeLexicalMatch(
                    chunk_id=row.chunk_id,
                    content_id=row.content_id,
                    document_id=row.document_id,
                    document_version_id=row.document_version_id,
                    source_code=source_code,
                    version_number=row.version_number,
                    document_kind=KnowledgeDocumentKind.GENERAL_REFERENCE,
                    match_weight=int(row.match_weight),
                    matched_term_count=int(row.matched_term_count),
                    chunk_position=int(row.chunk_position),
                )
            )
        return tuple(result)
