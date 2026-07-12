"""Mappers between analysis persistence records and ORM rows."""

from __future__ import annotations

from closeros.application.analysis_persistence import (
    ConversationAnalysisRunRecord,
    ConversationFindingEvidenceRecord,
    ConversationFindingKnowledgeCitationRecord,
    ConversationFindingRecord,
)
from closeros.infrastructure.analysis_orm import (
    ConversationAnalysisRunRow,
    ConversationFindingEvidenceRow,
    ConversationFindingKnowledgeCitationRow,
    ConversationFindingRow,
)


def analysis_run_to_row(record: ConversationAnalysisRunRecord) -> ConversationAnalysisRunRow:
    return ConversationAnalysisRunRow(
        id=record.id,
        tenant_id=record.tenant_id,
        conversation_thread_id=record.conversation_thread_id,
        policy_id=record.policy_id,
        purpose=record.purpose,
        status=record.status,
        prompt_version=record.prompt_version,
        rubric_version=record.rubric_version,
        input_digest=record.input_digest,
        knowledge_context_digest=record.knowledge_context_digest,
        output_digest=record.output_digest,
        model_provider=record.model_provider,
        input_token_count=record.input_token_count,
        output_token_count=record.output_token_count,
        cost_minor_units=record.cost_minor_units,
        requested_at=record.requested_at,
        completed_at=record.completed_at,
        failure_code=record.failure_code,
    )


def analysis_run_to_record(row: ConversationAnalysisRunRow) -> ConversationAnalysisRunRecord:
    return ConversationAnalysisRunRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_thread_id=row.conversation_thread_id,
        policy_id=row.policy_id,
        purpose=row.purpose,
        status=row.status,
        prompt_version=row.prompt_version,
        rubric_version=row.rubric_version,
        input_digest=row.input_digest,
        knowledge_context_digest=row.knowledge_context_digest,
        output_digest=row.output_digest,
        model_provider=row.model_provider,
        input_token_count=row.input_token_count,
        output_token_count=row.output_token_count,
        cost_minor_units=row.cost_minor_units,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        failure_code=row.failure_code,
    )


def finding_to_row(record: ConversationFindingRecord) -> ConversationFindingRow:
    return ConversationFindingRow(
        id=record.id,
        tenant_id=record.tenant_id,
        analysis_run_id=record.analysis_run_id,
        finding_code=record.finding_code,
        severity=record.severity,
        status=record.status,
        confidence_basis_points=record.confidence_basis_points,
        revenue_at_risk_basis_points=record.revenue_at_risk_basis_points,
        created_at=record.created_at,
        reviewed_at=record.reviewed_at,
    )


def finding_to_record(row: ConversationFindingRow) -> ConversationFindingRecord:
    return ConversationFindingRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        analysis_run_id=row.analysis_run_id,
        finding_code=row.finding_code,
        severity=row.severity,
        status=row.status,
        confidence_basis_points=row.confidence_basis_points,
        revenue_at_risk_basis_points=row.revenue_at_risk_basis_points,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def evidence_to_row(record: ConversationFindingEvidenceRecord) -> ConversationFindingEvidenceRow:
    return ConversationFindingEvidenceRow(
        id=record.id,
        tenant_id=record.tenant_id,
        finding_id=record.finding_id,
        conversation_thread_id=record.conversation_thread_id,
        message_id=record.message_id,
        excerpt_content_id=record.excerpt_content_id,
        created_at=record.created_at,
    )


def evidence_to_record(row: ConversationFindingEvidenceRow) -> ConversationFindingEvidenceRecord:
    return ConversationFindingEvidenceRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        finding_id=row.finding_id,
        conversation_thread_id=row.conversation_thread_id,
        message_id=row.message_id,
        excerpt_content_id=row.excerpt_content_id,
        created_at=row.created_at,
    )


def citation_to_row(
    record: ConversationFindingKnowledgeCitationRecord,
) -> ConversationFindingKnowledgeCitationRow:
    return ConversationFindingKnowledgeCitationRow(
        id=record.id,
        tenant_id=record.tenant_id,
        finding_id=record.finding_id,
        document_id=record.document_id,
        document_version_id=record.document_version_id,
        chunk_id=record.chunk_id,
        retrieval_rank=record.retrieval_rank,
        relevance_basis_points=record.relevance_basis_points,
        created_at=record.created_at,
    )


def citation_to_record(
    row: ConversationFindingKnowledgeCitationRow,
) -> ConversationFindingKnowledgeCitationRecord:
    return ConversationFindingKnowledgeCitationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        finding_id=row.finding_id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        chunk_id=row.chunk_id,
        retrieval_rank=row.retrieval_rank,
        relevance_basis_points=row.relevance_basis_points,
        created_at=row.created_at,
    )
