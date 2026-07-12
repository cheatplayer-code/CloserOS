"""Outbox handler for real `message.analyze` conversation analysis."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from closeros.application.ai_audit import (
    ai_budget_exceeded_event,
    analysis_blocked_event,
    analysis_completed_event,
    analysis_failed_event,
    analysis_requested_event,
)
from closeros.application.ai_gateway import (
    AiGateway,
    AiGatewayError,
    AiGatewayRequest,
    GatewayMessageInput,
)
from closeros.application.ai_policy_persistence import (
    AiUsageDailyRecord,
    TenantAiPolicyRecord,
)
from closeros.application.analysis_persistence import (
    ConversationAnalysisRunRecord,
    ConversationFindingEvidenceRecord,
    ConversationFindingKnowledgeCitationRecord,
    ConversationFindingRecord,
)
from closeros.application.audit_recording import AuditContext, append_required_audit_event
from closeros.application.content_encryption_service import ContentEncryptionService
from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.domain.ai_analysis import (
    AiBudget,
    AiFailureCode,
    AiProviderCode,
    AiPurpose,
    AiUsage,
    TenantAiPolicy,
)
from closeros.domain.audit import AuditActorType
from closeros.domain.encrypted_content import (
    ContentAccessPurpose,
    ContentEncoding,
    EncryptedContentKind,
)
from closeros.domain.outbox import OutboxErrorCode, OutboxJob
from closeros.infrastructure.canonical_orm import MessageRow
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork
from closeros.infrastructure.knowledge_orm import KnowledgeChunkRow, KnowledgeDocumentVersionRow

_UnitOfWorkFactory = Callable[[], IntegratedUnitOfWork]
_UuidFactory = Callable[[], UUID]
_Clock = Callable[[], datetime]

_ANALYSIS_PURPOSE_CODE = "quality_control"


class MessageAnalyzeHandlerError(Exception):
    def __init__(self, *, error_code: OutboxErrorCode, permanent: bool) -> None:
        self.error_code = error_code
        self.permanent = permanent
        super().__init__("message analyze failed")


def _require_session(uow: IntegratedUnitOfWork) -> AsyncSession:
    if not isinstance(uow, SqlAlchemyIntegratedUnitOfWork):
        raise MessageAnalyzeHandlerError(
            error_code=OutboxErrorCode.HANDLER_FAILED,
            permanent=True,
        )
    return uow.session


def _provider_code_for_storage(provider_code: AiProviderCode) -> str:
    if provider_code is AiProviderCode.OPENAI_COMPATIBLE:
        return "openai"
    return "local"


def _build_policy(record: TenantAiPolicyRecord, *, provider_code: AiProviderCode) -> TenantAiPolicy:
    return TenantAiPolicy(
        tenant_id=record.tenant_id,
        enabled=record.mode != "off",
        provider_code=provider_code,
        allowed_purposes=frozenset({AiPurpose.CONVERSATION_ANALYSIS}),
        processing_region_code="kz",
        prompt_version=record.prompt_version,
        rubric_version=record.rubric_version,
        maximum_messages_per_request=200,
        maximum_sanitized_characters=128_000,
        maximum_output_characters=32_768,
        daily_input_token_budget=500_000,
        daily_output_token_budget=500_000,
        daily_cost_budget_microunits=max(record.daily_budget_limit_minor_units, 1),
        maximum_retrieved_knowledge_chunks=8,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=1,
    )


def _estimate_usage(messages: tuple[GatewayMessageInput, ...]) -> AiUsage:
    total_chars = sum(len(item.sanitized_text) for item in messages)
    input_tokens = max(1, total_chars // 4)
    output_tokens = max(64, input_tokens // 4)
    return AiUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_milliseconds=0,
        estimated_cost_microunits=0,
    )


def _knowledge_digest(chunk_ids: tuple[UUID, ...]) -> bytes:
    joined = ",".join(str(value) for value in sorted(chunk_ids, key=str))
    return hashlib.sha256(joined.encode("utf-8")).digest()


def _budget_consumed_bps(*, consumed: int, limit: int) -> int:
    if limit <= 0:
        return 10_000
    return min(10_000, int((consumed * 10_000) / limit))


@dataclass(frozen=True, slots=True)
class MessageAnalyzeHandler:
    uow_factory: _UnitOfWorkFactory
    content_encryption: ContentEncryptionService
    ai_gateway: AiGateway
    service_actor_id: UUID
    provider_code: AiProviderCode
    uuid_factory: _UuidFactory
    clock: _Clock

    async def handle(self, *, job: OutboxJob) -> None:
        if job.tenant_id is None or job.reference.resource_type != "message":
            raise MessageAnalyzeHandlerError(
                error_code=OutboxErrorCode.MALFORMED_PROVIDER_EVENT,
                permanent=True,
            )

        tenant_id = job.tenant_id
        message_id = job.reference.resource_id
        occurred_at = self.clock()
        correlation = AuditContext(correlation_id=job.id)

        run_id = self.uuid_factory()
        try:
            policy_record = await self._load_policy(tenant_id=tenant_id)
            if policy_record is None or policy_record.mode == "off":
                await self._record_blocked_without_run(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code=AiFailureCode.POLICY_DISABLED.value,
                    provider_code=_provider_code_for_storage(self.provider_code),
                    occurred_at=occurred_at,
                    audit_context=correlation,
                )
                return

            messages = await self._load_sanitized_messages(
                tenant_id=tenant_id,
                anchor_message_id=message_id,
                occurred_at=occurred_at,
                audit_context=correlation,
            )
            if not messages:
                await self._record_blocked_without_run(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code=AiFailureCode.SANITIZATION_MISSING.value,
                    provider_code=_provider_code_for_storage(self.provider_code),
                    occurred_at=occurred_at,
                    audit_context=correlation,
                )
                return

            policy = _build_policy(policy_record, provider_code=self.provider_code)
            usage_daily = await self._load_usage_daily(
                tenant_id=tenant_id,
                usage_date=occurred_at.date(),
                model_provider=_provider_code_for_storage(self.provider_code),
            )
            current_budget = AiBudget(
                daily_input_token_budget=policy.daily_input_token_budget,
                daily_output_token_budget=policy.daily_output_token_budget,
                daily_cost_budget_microunits=policy.daily_cost_budget_microunits,
                consumed_input_tokens=0 if usage_daily is None else usage_daily.input_token_count,
                consumed_output_tokens=0 if usage_daily is None else usage_daily.output_token_count,
                consumed_cost_microunits=0 if usage_daily is None else usage_daily.cost_minor_units,
            )
            run = ConversationAnalysisRunRecord(
                id=run_id,
                tenant_id=tenant_id,
                conversation_thread_id=messages[0].message_id,  # temporary, replaced below
                policy_id=policy_record.id,
                purpose=_ANALYSIS_PURPOSE_CODE,
                status="requested",
                prompt_version=policy.prompt_version,
                rubric_version=policy.rubric_version,
                input_digest=hashlib.sha256(b"pending").digest(),
                knowledge_context_digest=hashlib.sha256(b"pending").digest(),
                output_digest=None,
                model_provider=_provider_code_for_storage(self.provider_code),
                input_token_count=0,
                output_token_count=0,
                cost_minor_units=0,
                requested_at=occurred_at,
                completed_at=None,
                failure_code=None,
            )
            conversation_thread_id = await self._load_conversation_thread_id(
                tenant_id=tenant_id,
                message_id=message_id,
            )
            if conversation_thread_id is None:
                raise MessageAnalyzeHandlerError(
                    error_code=OutboxErrorCode.MISSING_CANONICAL_PARENT,
                    permanent=True,
                )
            run = replace(run, conversation_thread_id=conversation_thread_id)
            await self._append_requested_run(
                run=run,
                provider_code=_provider_code_for_storage(self.provider_code),
                occurred_at=occurred_at,
                audit_context=correlation,
            )

            gateway_request = AiGatewayRequest(
                tenant_id=tenant_id,
                policy=policy,
                purpose=AiPurpose.CONVERSATION_ANALYSIS,
                model_code="conversation-analysis-v1",
                messages=messages,
                current_budget=current_budget,
                estimated_usage=_estimate_usage(messages),
            )
            try:
                gateway_result = await self.ai_gateway.analyze_conversation(request=gateway_request)
            except AiGatewayError as error:
                await self._record_blocked_run(
                    run=run,
                    failure_code=error.failure_code,
                    provider_code=_provider_code_for_storage(self.provider_code),
                    occurred_at=occurred_at,
                    audit_context=correlation,
                )
                if error.failure_code is AiFailureCode.BUDGET_EXCEEDED:
                    await self._record_budget_exceeded(
                        tenant_id=tenant_id,
                        run_id=run.id,
                        provider_code=_provider_code_for_storage(self.provider_code),
                        occurred_at=occurred_at,
                        audit_context=correlation,
                    )
                return

            await self._record_completed_run(
                run=run,
                conversation_thread_id=conversation_thread_id,
                gateway_result=gateway_result,
                usage_daily=usage_daily,
                policy_record=policy_record,
                occurred_at=occurred_at,
                audit_context=correlation,
            )
        except MessageAnalyzeHandlerError:
            raise
        except Exception as error:
            await self._record_failed_without_run(
                tenant_id=tenant_id,
                run_id=run_id,
                provider_code=_provider_code_for_storage(self.provider_code),
                occurred_at=occurred_at,
                audit_context=correlation,
                error_class=type(error).__name__,
            )
            raise MessageAnalyzeHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=False,
            ) from error

    async def _load_policy(self, *, tenant_id: UUID) -> TenantAiPolicyRecord | None:
        uow = self.uow_factory()
        async with uow:
            return await uow.tenant_ai_policies.get_by_tenant_id(tenant_id=tenant_id)

    async def _load_usage_daily(
        self,
        *,
        tenant_id: UUID,
        usage_date: date,
        model_provider: str,
    ) -> AiUsageDailyRecord | None:
        uow = self.uow_factory()
        async with uow:
            return await uow.ai_usage_daily.get_by_usage_key(
                tenant_id=tenant_id,
                usage_date=usage_date,
                dimension="analysis",
                model_provider=model_provider,
            )

    async def _load_conversation_thread_id(
        self,
        *,
        tenant_id: UUID,
        message_id: UUID,
    ) -> UUID | None:
        uow = self.uow_factory()
        async with uow:
            message = await uow.messages.get_by_id(tenant_id=tenant_id, message_id=message_id)
            return None if message is None else message.conversation_thread_id

    async def _load_sanitized_messages(
        self,
        *,
        tenant_id: UUID,
        anchor_message_id: UUID,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> tuple[GatewayMessageInput, ...]:
        uow = self.uow_factory()
        async with uow:
            anchor = await uow.messages.get_by_id(tenant_id=tenant_id, message_id=anchor_message_id)
            if anchor is None:
                return ()
            session = _require_session(uow)
            message_rows = (
                (
                    await session.execute(
                        select(MessageRow).where(
                            MessageRow.tenant_id == tenant_id,
                            MessageRow.conversation_thread_id == anchor.conversation_thread_id,
                        )
                    )
                )
                .scalars()
                .all()
            )

        ordered_rows = tuple(sorted(message_rows, key=lambda row: (row.sent_at, str(row.id))))
        result: list[GatewayMessageInput] = []
        for row in ordered_rows:
            if row.content_id is None:
                continue
            policy_version = "lm-policy-v1"
            uow = self.uow_factory()
            async with uow:
                sanitization = await uow.content_sanitizations.get_completed_by_source(
                    tenant_id=tenant_id,
                    source_content_id=row.content_id,
                    policy_version=policy_version,
                )
            if sanitization is None or sanitization.sanitized_content_id is None:
                continue
            decrypted = await self.content_encryption.load_and_decrypt(
                tenant_id=tenant_id,
                content_id=sanitization.sanitized_content_id,
                purpose=ContentAccessPurpose.AI_ANALYSIS,
                occurred_at=occurred_at,
                audit_context=audit_context,
                actor_type=AuditActorType.SERVICE,
                actor_id=self.service_actor_id,
                audit_event_id=self.uuid_factory(),
            )
            if (
                decrypted.kind is not EncryptedContentKind.SANITIZED_MESSAGE
                or decrypted.encoding is not ContentEncoding.UTF8
            ):
                continue
            result.append(
                GatewayMessageInput(
                    message_id=row.id,
                    sender_role=row.sender_type,
                    sent_at=row.sent_at,
                    content_kind=decrypted.kind,
                    access_purpose=ContentAccessPurpose.AI_ANALYSIS,
                    sanitized_text=decrypted.as_utf8_text(),
                )
            )
        return tuple(result)

    async def _append_requested_run(
        self,
        *,
        run: ConversationAnalysisRunRecord,
        provider_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            await uow.conversation_analysis_runs.add(record=run)
            await append_required_audit_event(
                uow.audit_events,
                analysis_requested_event(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    provider_code=provider_code,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    prompt_version=run.prompt_version,
                    rubric_version=run.rubric_version,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _record_blocked_run(
        self,
        *,
        run: ConversationAnalysisRunRecord,
        failure_code: AiFailureCode,
        provider_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        blocked = replace(
            run,
            status="blocked",
            completed_at=occurred_at,
            failure_code=failure_code.value,
        )
        uow = self.uow_factory()
        async with uow:
            await uow.conversation_analysis_runs.update(record=blocked)
            await append_required_audit_event(
                uow.audit_events,
                analysis_blocked_event(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    reason_code=failure_code.value,
                    budget_status="exceeded"
                    if failure_code is AiFailureCode.BUDGET_EXCEEDED
                    else "not_applicable",
                    provider_code=provider_code,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _record_completed_run(
        self,
        *,
        run: ConversationAnalysisRunRecord,
        conversation_thread_id: UUID,
        gateway_result: object,
        usage_daily: AiUsageDailyRecord | None,
        policy_record: TenantAiPolicyRecord,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        from closeros.application.ai_gateway import AiGatewayResult

        result = gateway_result
        if not isinstance(result, AiGatewayResult):
            raise MessageAnalyzeHandlerError(
                error_code=OutboxErrorCode.HANDLER_FAILED,
                permanent=False,
            )
        completed_run = replace(
            run,
            status="completed",
            input_digest=result.input_digest,
            knowledge_context_digest=_knowledge_digest(
                tuple(item.chunk_id for item in result.retrieved_knowledge)
            ),
            output_digest=result.output_digest,
            model_provider=result.provider_code
            if result.provider_code in {"openai", "deepseek", "anthropic", "local"}
            else "local",
            input_token_count=result.usage.input_tokens,
            output_token_count=result.usage.output_tokens,
            cost_minor_units=result.usage.estimated_cost_microunits,
            completed_at=occurred_at,
            failure_code=None,
        )
        findings: list[ConversationFindingRecord] = []
        evidence_records: list[ConversationFindingEvidenceRecord] = []
        citation_records: list[ConversationFindingKnowledgeCitationRecord] = []
        chunk_lookup = await self._load_chunk_lookup(
            tenant_id=run.tenant_id,
            chunk_ids=tuple(c.chunk_id for f in result.findings for c in f.knowledge_citations),
        )
        for finding in result.findings:
            finding_id = self.uuid_factory()
            findings.append(
                ConversationFindingRecord(
                    id=finding_id,
                    tenant_id=run.tenant_id,
                    analysis_run_id=run.id,
                    finding_code="missing_next_step"
                    if finding.issue_code.value not in _FINDING_CODE_VALUES
                    else finding.issue_code.value,
                    severity=finding.severity.value,
                    status="open",
                    confidence_basis_points=finding.confidence_basis_points,
                    revenue_at_risk_basis_points=None,
                    created_at=occurred_at,
                    reviewed_at=None,
                )
            )
            for evidence in finding.evidence:
                evidence_records.append(
                    ConversationFindingEvidenceRecord(
                        id=self.uuid_factory(),
                        tenant_id=run.tenant_id,
                        finding_id=finding_id,
                        conversation_thread_id=conversation_thread_id,
                        message_id=evidence.message_id,
                        excerpt_content_id=None,
                        created_at=occurred_at,
                    )
                )
            rank = 1
            for citation in finding.knowledge_citations:
                chunk_meta = chunk_lookup.get(citation.chunk_id)
                if chunk_meta is None:
                    continue
                citation_records.append(
                    ConversationFindingKnowledgeCitationRecord(
                        id=self.uuid_factory(),
                        tenant_id=run.tenant_id,
                        finding_id=finding_id,
                        document_id=chunk_meta[0],
                        document_version_id=chunk_meta[1],
                        chunk_id=citation.chunk_id,
                        retrieval_rank=rank,
                        relevance_basis_points=5_000,
                        created_at=occurred_at,
                    )
                )
                rank += 1

        consumed_cost = result.usage.estimated_cost_microunits + (
            0 if usage_daily is None else usage_daily.cost_minor_units
        )
        usage_record = AiUsageDailyRecord(
            id=self.uuid_factory() if usage_daily is None else usage_daily.id,
            tenant_id=run.tenant_id,
            usage_date=occurred_at.date(),
            dimension="analysis",
            model_provider=completed_run.model_provider,
            input_token_count=result.usage.input_tokens
            + (0 if usage_daily is None else usage_daily.input_token_count),
            output_token_count=result.usage.output_tokens
            + (0 if usage_daily is None else usage_daily.output_token_count),
            requests_count=1 + (0 if usage_daily is None else usage_daily.requests_count),
            cost_minor_units=consumed_cost,
            budget_limit_minor_units=policy_record.daily_budget_limit_minor_units,
            budget_consumed_basis_points=_budget_consumed_bps(
                consumed=consumed_cost,
                limit=policy_record.daily_budget_limit_minor_units,
            ),
            last_recorded_at=occurred_at,
        )

        uow = self.uow_factory()
        async with uow:
            await uow.conversation_analysis_runs.update(record=completed_run)
            await uow.conversation_findings.replace_for_run(
                tenant_id=run.tenant_id,
                analysis_run_id=run.id,
                findings=tuple(findings),
            )
            finding_ids = tuple(item.id for item in findings)
            await uow.conversation_finding_evidence.replace_for_findings(
                tenant_id=run.tenant_id,
                finding_ids=finding_ids,
                evidence=tuple(evidence_records),
            )
            await uow.conversation_finding_knowledge_citations.replace_for_findings(
                tenant_id=run.tenant_id,
                finding_ids=finding_ids,
                citations=tuple(citation_records),
            )
            await uow.ai_usage_daily.upsert(record=usage_record)
            await append_required_audit_event(
                uow.audit_events,
                analysis_completed_event(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    issue_count=len(findings),
                    citation_count=len(citation_records),
                    token_count=result.usage.input_tokens + result.usage.output_tokens,
                    latency_bucket=_latency_bucket(result.usage.latency_milliseconds),
                    provider_code=completed_run.model_provider,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    rubric_version=completed_run.rubric_version,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _load_chunk_lookup(
        self,
        *,
        tenant_id: UUID,
        chunk_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[UUID, UUID]]:
        if not chunk_ids:
            return {}
        uow = self.uow_factory()
        async with uow:
            session = _require_session(uow)
            rows = (
                await session.execute(
                    select(
                        KnowledgeChunkRow.id,
                        KnowledgeDocumentVersionRow.document_id,
                        KnowledgeChunkRow.document_version_id,
                    )
                    .join(
                        KnowledgeDocumentVersionRow,
                        (KnowledgeDocumentVersionRow.id == KnowledgeChunkRow.document_version_id)
                        & (KnowledgeDocumentVersionRow.tenant_id == KnowledgeChunkRow.tenant_id),
                    )
                    .where(
                        KnowledgeChunkRow.tenant_id == tenant_id,
                        KnowledgeChunkRow.id.in_(chunk_ids),
                    )
                )
            ).all()
            return {row.id: (row.document_id, row.document_version_id) for row in rows}

    async def _record_failed_without_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        provider_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
        error_class: str,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            await append_required_audit_event(
                uow.audit_events,
                analysis_failed_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code="handler_failed",
                    error_class=error_class.lower(),
                    provider_code=provider_code,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _record_blocked_without_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        reason_code: str,
        provider_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            await append_required_audit_event(
                uow.audit_events,
                analysis_blocked_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason_code=reason_code,
                    budget_status="not_applicable",
                    provider_code=provider_code,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()

    async def _record_budget_exceeded(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        provider_code: str,
        occurred_at: datetime,
        audit_context: AuditContext,
    ) -> None:
        uow = self.uow_factory()
        async with uow:
            await append_required_audit_event(
                uow.audit_events,
                ai_budget_exceeded_event(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    provider_code=provider_code,
                    purpose_code=AiPurpose.CONVERSATION_ANALYSIS.value,
                    occurred_at=occurred_at,
                    audit_context=audit_context,
                    actor_type=AuditActorType.SERVICE,
                    actor_id=self.service_actor_id,
                    event_id=self.uuid_factory(),
                ),
            )
            await uow.commit()


_FINDING_CODE_VALUES = {
    "missing_follow_up",
    "slow_response",
    "missing_next_step",
    "potential_loss_risk",
    "policy_violation",
}


def _latency_bucket(latency_ms: int) -> str:
    if latency_ms <= 500:
        return "lte_500ms"
    if latency_ms <= 2_000:
        return "lte_2s"
    return "gt_2s"
