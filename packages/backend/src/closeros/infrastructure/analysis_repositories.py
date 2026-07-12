"""PostgreSQL repositories for conversation analysis runs and findings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.analysis_persistence import (
    AnalysisPersistenceError,
    ConversationAnalysisRunNotFoundError,
    ConversationAnalysisRunRecord,
    ConversationFindingEvidenceRecord,
    ConversationFindingKnowledgeCitationRecord,
    ConversationFindingRecord,
    DuplicateConversationAnalysisRunError,
)
from closeros.infrastructure import analysis_mappers as mappers
from closeros.infrastructure.analysis_orm import (
    ConversationAnalysisRunRow,
    ConversationFindingEvidenceRow,
    ConversationFindingKnowledgeCitationRow,
    ConversationFindingRow,
)
from closeros.infrastructure.persistence_errors import translate_integrity_error

_CONSTRAINT_ERRORS: dict[str, type[AnalysisPersistenceError]] = {
    (
        "uq_conversation_analysis_runs_tenant_conversation_thread_id_"
        "purpose_prompt_version_rubric_version_input_digest_"
        "knowledge_context_digest"
    ): DuplicateConversationAnalysisRunError,
}


def _translate_integrity_error(error: IntegrityError) -> AnalysisPersistenceError:
    return translate_integrity_error(
        error,
        constraint_errors=_CONSTRAINT_ERRORS,
        default=AnalysisPersistenceError,
        message="analysis persistence integrity error",
    )


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        raise _translate_integrity_error(error) from error


class SqlAlchemyConversationAnalysisRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, record: ConversationAnalysisRunRecord) -> None:
        self._session.add(mappers.analysis_run_to_row(record))
        await _flush(self._session)

    async def get_by_id(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> ConversationAnalysisRunRecord | None:
        row = await self._session.get(ConversationAnalysisRunRow, run_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return mappers.analysis_run_to_record(row)

    async def get_by_id_for_update(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> ConversationAnalysisRunRecord | None:
        row = (
            await self._session.execute(
                select(ConversationAnalysisRunRow)
                .where(
                    ConversationAnalysisRunRow.id == run_id,
                    ConversationAnalysisRunRow.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return None if row is None else mappers.analysis_run_to_record(row)

    async def update(self, *, record: ConversationAnalysisRunRecord) -> None:
        row = (
            await self._session.execute(
                select(ConversationAnalysisRunRow)
                .where(
                    ConversationAnalysisRunRow.id == record.id,
                    ConversationAnalysisRunRow.tenant_id == record.tenant_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise ConversationAnalysisRunNotFoundError("analysis run not found")
        row.status = record.status
        row.output_digest = record.output_digest
        row.model_provider = record.model_provider
        row.input_token_count = record.input_token_count
        row.output_token_count = record.output_token_count
        row.cost_minor_units = record.cost_minor_units
        row.completed_at = record.completed_at
        row.failure_code = record.failure_code
        row.prompt_version = record.prompt_version
        row.rubric_version = record.rubric_version
        row.input_digest = record.input_digest
        row.knowledge_context_digest = record.knowledge_context_digest
        await _flush(self._session)

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[ConversationAnalysisRunRecord, ...]:
        statement = select(ConversationAnalysisRunRow).where(
            ConversationAnalysisRunRow.tenant_id == tenant_id
        )
        if conversation_thread_id is not None:
            statement = statement.where(
                ConversationAnalysisRunRow.conversation_thread_id == conversation_thread_id
            )
        statement = statement.order_by(
            ConversationAnalysisRunRow.requested_at.desc(),
            ConversationAnalysisRunRow.id.desc(),
        ).limit(limit)
        rows = (await self._session.execute(statement)).scalars().all()
        return tuple(mappers.analysis_run_to_record(row) for row in rows)


class SqlAlchemyConversationFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_run(
        self,
        *,
        tenant_id: UUID,
        analysis_run_id: UUID,
        findings: tuple[ConversationFindingRecord, ...],
    ) -> None:
        await self._session.execute(
            delete(ConversationFindingRow).where(
                ConversationFindingRow.tenant_id == tenant_id,
                ConversationFindingRow.analysis_run_id == analysis_run_id,
            )
        )
        for finding in findings:
            self._session.add(mappers.finding_to_row(finding))
        await _flush(self._session)

    async def list_by_run(
        self,
        *,
        tenant_id: UUID,
        analysis_run_id: UUID,
    ) -> tuple[ConversationFindingRecord, ...]:
        rows = (
            (
                await self._session.execute(
                    select(ConversationFindingRow)
                    .where(
                        ConversationFindingRow.tenant_id == tenant_id,
                        ConversationFindingRow.analysis_run_id == analysis_run_id,
                    )
                    .order_by(
                        ConversationFindingRow.created_at.asc(),
                        ConversationFindingRow.id.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return tuple(mappers.finding_to_record(row) for row in rows)


class SqlAlchemyConversationFindingEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_findings(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
        evidence: tuple[ConversationFindingEvidenceRecord, ...],
    ) -> None:
        if finding_ids:
            await self._session.execute(
                delete(ConversationFindingEvidenceRow).where(
                    ConversationFindingEvidenceRow.tenant_id == tenant_id,
                    ConversationFindingEvidenceRow.finding_id.in_(finding_ids),
                )
            )
        for item in evidence:
            self._session.add(mappers.evidence_to_row(item))
        await _flush(self._session)

    async def list_by_finding_ids(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
    ) -> tuple[ConversationFindingEvidenceRecord, ...]:
        if not finding_ids:
            return ()
        rows = (
            (
                await self._session.execute(
                    select(ConversationFindingEvidenceRow)
                    .where(
                        ConversationFindingEvidenceRow.tenant_id == tenant_id,
                        ConversationFindingEvidenceRow.finding_id.in_(finding_ids),
                    )
                    .order_by(
                        ConversationFindingEvidenceRow.finding_id.asc(),
                        ConversationFindingEvidenceRow.created_at.asc(),
                        ConversationFindingEvidenceRow.id.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return tuple(mappers.evidence_to_record(row) for row in rows)


class SqlAlchemyConversationFindingKnowledgeCitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_findings(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
        citations: tuple[ConversationFindingKnowledgeCitationRecord, ...],
    ) -> None:
        if finding_ids:
            await self._session.execute(
                delete(ConversationFindingKnowledgeCitationRow).where(
                    ConversationFindingKnowledgeCitationRow.tenant_id == tenant_id,
                    ConversationFindingKnowledgeCitationRow.finding_id.in_(finding_ids),
                )
            )
        for item in citations:
            self._session.add(mappers.citation_to_row(item))
        await _flush(self._session)

    async def list_by_finding_ids(
        self,
        *,
        tenant_id: UUID,
        finding_ids: tuple[UUID, ...],
    ) -> tuple[ConversationFindingKnowledgeCitationRecord, ...]:
        if not finding_ids:
            return ()
        rows = (
            (
                await self._session.execute(
                    select(ConversationFindingKnowledgeCitationRow)
                    .where(
                        ConversationFindingKnowledgeCitationRow.tenant_id == tenant_id,
                        ConversationFindingKnowledgeCitationRow.finding_id.in_(finding_ids),
                    )
                    .order_by(
                        ConversationFindingKnowledgeCitationRow.finding_id.asc(),
                        ConversationFindingKnowledgeCitationRow.retrieval_rank.asc(),
                        ConversationFindingKnowledgeCitationRow.id.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return tuple(mappers.citation_to_record(row) for row in rows)
