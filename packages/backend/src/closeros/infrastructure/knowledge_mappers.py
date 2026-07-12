"""Mappers between knowledge persistence records and SQLAlchemy rows."""

from __future__ import annotations

from closeros.application.knowledge_persistence import (
    KnowledgeChunkRecord,
    KnowledgeChunkTermRecord,
    KnowledgeDocumentRecord,
    KnowledgeDocumentVersionRecord,
)
from closeros.infrastructure.knowledge_orm import (
    KnowledgeChunkRow,
    KnowledgeChunkTermRow,
    KnowledgeDocumentRow,
    KnowledgeDocumentVersionRow,
)


def document_to_row(record: KnowledgeDocumentRecord) -> KnowledgeDocumentRow:
    return KnowledgeDocumentRow(
        id=record.id,
        tenant_id=record.tenant_id,
        source_type=record.source_type,
        external_reference=record.external_reference,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def document_to_record(row: KnowledgeDocumentRow) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        source_type=row.source_type,
        external_reference=row.external_reference,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def version_to_row(record: KnowledgeDocumentVersionRecord) -> KnowledgeDocumentVersionRow:
    return KnowledgeDocumentVersionRow(
        id=record.id,
        tenant_id=record.tenant_id,
        document_id=record.document_id,
        version_number=record.version_number,
        status=record.status,
        content_id=record.content_id,
        content_sha256_digest=record.content_sha256_digest,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        created_at=record.created_at,
        approved_at=record.approved_at,
        indexed_at=record.indexed_at,
        revoked_at=record.revoked_at,
    )


def version_to_record(row: KnowledgeDocumentVersionRow) -> KnowledgeDocumentVersionRecord:
    return KnowledgeDocumentVersionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        document_id=row.document_id,
        version_number=row.version_number,
        status=row.status,
        content_id=row.content_id,
        content_sha256_digest=row.content_sha256_digest,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        created_at=row.created_at,
        approved_at=row.approved_at,
        indexed_at=row.indexed_at,
        revoked_at=row.revoked_at,
    )


def chunk_to_row(record: KnowledgeChunkRecord) -> KnowledgeChunkRow:
    return KnowledgeChunkRow(
        id=record.id,
        tenant_id=record.tenant_id,
        document_version_id=record.document_version_id,
        content_id=record.content_id,
        position=record.position,
        status=record.status,
        chunk_sha256_digest=record.chunk_sha256_digest,
        token_count=record.token_count,
        created_at=record.created_at,
    )


def chunk_to_record(row: KnowledgeChunkRow) -> KnowledgeChunkRecord:
    return KnowledgeChunkRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        document_version_id=row.document_version_id,
        content_id=row.content_id,
        position=row.position,
        status=row.status,
        chunk_sha256_digest=row.chunk_sha256_digest,
        token_count=row.token_count,
        created_at=row.created_at,
    )


def chunk_term_to_row(record: KnowledgeChunkTermRecord) -> KnowledgeChunkTermRow:
    return KnowledgeChunkTermRow(
        chunk_id=record.chunk_id,
        tenant_id=record.tenant_id,
        term_digest=record.term_digest,
        weight_basis_points=record.weight_basis_points,
    )
