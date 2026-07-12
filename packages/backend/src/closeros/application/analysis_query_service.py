"""Tenant-scoped query service for conversation analysis runs and findings."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from closeros.application.analysis_persistence import (
    ConversationAnalysisRunRecord,
    ConversationFindingEvidenceRecord,
    ConversationFindingKnowledgeCitationRecord,
    ConversationFindingRecord,
)
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]


@dataclass(frozen=True, slots=True)
class AnalysisFindingView:
    finding: ConversationFindingRecord
    evidence: tuple[ConversationFindingEvidenceRecord, ...]
    citations: tuple[ConversationFindingKnowledgeCitationRecord, ...]


@dataclass(frozen=True, slots=True)
class AnalysisRunView:
    run: ConversationAnalysisRunRecord
    findings: tuple[AnalysisFindingView, ...]


class AnalysisQueryService:
    def __init__(self, *, uow_factory: _UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list_runs(
        self,
        *,
        tenant_id: UUID,
        conversation_thread_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[AnalysisRunView, ...]:
        uow = self._uow_factory()
        async with uow:
            runs = await uow.conversation_analysis_runs.list_by_tenant(
                tenant_id=tenant_id,
                conversation_thread_id=conversation_thread_id,
                limit=limit,
            )
            if not runs:
                return ()

            run_views: list[AnalysisRunView] = []
            for run in runs:
                findings = await uow.conversation_findings.list_by_run(
                    tenant_id=tenant_id,
                    analysis_run_id=run.id,
                )
                finding_ids = tuple(finding.id for finding in findings)
                evidence = await uow.conversation_finding_evidence.list_by_finding_ids(
                    tenant_id=tenant_id,
                    finding_ids=finding_ids,
                )
                citations = await uow.conversation_finding_knowledge_citations.list_by_finding_ids(
                    tenant_id=tenant_id,
                    finding_ids=finding_ids,
                )
                evidence_by_finding: dict[UUID, list[ConversationFindingEvidenceRecord]] = (
                    defaultdict(list)
                )
                for evidence_item in evidence:
                    evidence_by_finding[evidence_item.finding_id].append(evidence_item)
                citations_by_finding: dict[
                    UUID, list[ConversationFindingKnowledgeCitationRecord]
                ] = defaultdict(list)
                for citation_item in citations:
                    citations_by_finding[citation_item.finding_id].append(citation_item)
                finding_views = tuple(
                    AnalysisFindingView(
                        finding=finding,
                        evidence=tuple(evidence_by_finding.get(finding.id, ())),
                        citations=tuple(citations_by_finding.get(finding.id, ())),
                    )
                    for finding in findings
                )
                run_views.append(AnalysisRunView(run=run, findings=finding_views))
            return tuple(run_views)
