"""Application-layer AI gateway orchestration for NOPQ conversation analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from closeros.application.ai_budget_service import AiBudgetService, BudgetReservation
from closeros.application.ai_input_gate import (
    AiGateAcceptedInput,
    AiInputGate,
    AiInputGateError,
    GateMessage,
)
from closeros.application.ai_output_validator import (
    AiOutputValidationError,
    AiOutputValidator,
    ValidatedAiOutput,
)
from closeros.application.ai_ports import (
    AiClock,
    AiCredentialResolver,
    AiProviderRegistry,
    ProviderRequest,
)
from closeros.application.ai_prompt_builder import AiPromptBuilder
from closeros.application.conversation_input_assembler import (
    AssembledConversationInput,
    ConversationInputAssembler,
    SanitizedConversationMessage,
)
from closeros.domain.ai_analysis import (
    AiBudget,
    AiFailureCode,
    AiPurpose,
    AiUsage,
    ConversationFinding,
    TenantAiPolicy,
)
from closeros.domain.encrypted_content import ContentAccessPurpose, EncryptedContentKind
from closeros.domain.knowledge import KnowledgeRetrievalResult


class AiGatewayError(Exception):
    """Raised when AI gateway processing fails safely."""

    def __init__(self, *, failure_code: AiFailureCode) -> None:
        self.failure_code = failure_code
        super().__init__("ai gateway failed")


class KnowledgeRetrievalPort(Protocol):
    async def retrieve_for_conversation(
        self,
        *,
        tenant_id: UUID,
        purpose: AiPurpose,
        query_text: str,
        max_chunks: int,
    ) -> tuple[KnowledgeRetrievalResult, ...]: ...


@dataclass(frozen=True, slots=True)
class GatewayMessageInput:
    message_id: UUID
    sender_role: str
    sent_at: datetime
    content_kind: EncryptedContentKind
    access_purpose: ContentAccessPurpose
    sanitized_text: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, UUID):
            raise TypeError("message_id must be a UUID")
        if type(self.sender_role) is not str or not self.sender_role.strip():
            raise ValueError("sender_role must be a non-empty string")
        if not isinstance(self.sent_at, datetime):
            raise TypeError("sent_at must be a datetime")
        if self.sent_at.tzinfo is None or self.sent_at.utcoffset() is None:
            raise ValueError("sent_at must be timezone-aware")
        if not isinstance(self.content_kind, EncryptedContentKind):
            raise TypeError("content_kind must be an EncryptedContentKind")
        if not isinstance(self.access_purpose, ContentAccessPurpose):
            raise TypeError("access_purpose must be a ContentAccessPurpose")
        if type(self.sanitized_text) is not str or not self.sanitized_text.strip():
            raise ValueError("sanitized_text must be non-empty")


@dataclass(frozen=True, slots=True)
class AiGatewayRequest:
    tenant_id: UUID
    policy: TenantAiPolicy
    purpose: AiPurpose
    model_code: str
    messages: tuple[GatewayMessageInput, ...]
    current_budget: AiBudget
    estimated_usage: AiUsage

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        if not isinstance(self.policy, TenantAiPolicy):
            raise TypeError("policy must be a TenantAiPolicy")
        if not isinstance(self.purpose, AiPurpose):
            raise TypeError("purpose must be an AiPurpose")
        if type(self.model_code) is not str or not self.model_code.strip():
            raise ValueError("model_code must be a non-empty string")
        if not isinstance(self.messages, tuple) or not self.messages:
            raise ValueError("messages must be a non-empty tuple")
        if not all(isinstance(item, GatewayMessageInput) for item in self.messages):
            raise TypeError("messages must contain GatewayMessageInput values")
        if not isinstance(self.current_budget, AiBudget):
            raise TypeError("current_budget must be an AiBudget")
        if not isinstance(self.estimated_usage, AiUsage):
            raise TypeError("estimated_usage must be an AiUsage")


@dataclass(frozen=True, slots=True)
class AiGatewayResult:
    findings: tuple[ConversationFinding, ...]
    usage: AiUsage
    reservation: BudgetReservation
    input_digest: bytes = field(repr=False)
    output_digest: bytes = field(repr=False)
    prompt_version: str
    rubric_version: str
    provider_code: str
    model_code: str
    validated_output_json: str = field(repr=False)
    retrieved_knowledge: tuple[KnowledgeRetrievalResult, ...]


@dataclass(frozen=True, slots=True)
class AiGateway:
    external_calls_enabled: bool
    clock: AiClock
    input_gate: AiInputGate
    assembler: ConversationInputAssembler
    prompt_builder: AiPromptBuilder
    output_validator: AiOutputValidator
    budget_service: AiBudgetService
    provider_registry: AiProviderRegistry
    credential_resolver: AiCredentialResolver
    knowledge_retrieval: KnowledgeRetrievalPort

    async def analyze_conversation(self, *, request: AiGatewayRequest) -> AiGatewayResult:
        if request.purpose is not AiPurpose.CONVERSATION_ANALYSIS:
            raise AiGatewayError(failure_code=AiFailureCode.PURPOSE_NOT_ALLOWED)
        if not self.external_calls_enabled:
            raise AiGatewayError(failure_code=AiFailureCode.EXTERNAL_CALLS_DISABLED)

        assembled = self._assemble_messages(messages=request.messages)
        gated = self._gate_input(
            tenant_id=request.tenant_id,
            policy=request.policy,
            purpose=request.purpose,
            gate_messages=assembled.ordered_messages,
        )
        reservation = self.budget_service.reserve(
            current_budget=request.current_budget,
            requested_input_tokens=request.estimated_usage.input_tokens,
            requested_output_tokens=request.estimated_usage.output_tokens,
            requested_cost_microunits=request.estimated_usage.estimated_cost_microunits,
        )
        if not reservation.approved:
            raise AiGatewayError(failure_code=AiFailureCode.BUDGET_EXCEEDED)

        knowledge = await self.knowledge_retrieval.retrieve_for_conversation(
            tenant_id=request.tenant_id,
            purpose=request.purpose,
            query_text=gated.input_text,
            max_chunks=request.policy.maximum_retrieved_knowledge_chunks,
        )
        prompt_bundle = self.prompt_builder.build_conversation_analysis_prompt(
            sanitized_transcript=assembled.rendered_transcript,
            knowledge_results=knowledge,
            prompt_version=request.policy.prompt_version,
            rubric_version=request.policy.rubric_version,
        )

        provider = self.provider_registry.get_provider(provider_code=request.policy.provider_code)
        bearer_key = await self.credential_resolver.resolve_bearer_key(
            tenant_id=request.tenant_id,
            provider_code=request.policy.provider_code,
        )
        if bearer_key is None:
            raise AiGatewayError(failure_code=AiFailureCode.PROVIDER_UNAVAILABLE)

        provider_result = await provider.call_chat_json(
            request=ProviderRequest(
                tenant_id=request.tenant_id,
                provider_code=request.policy.provider_code,
                purpose=request.purpose,
                model_code=request.model_code,
                prompt_version=prompt_bundle.prompt_version,
                rubric_version=prompt_bundle.rubric_version,
                prompt_text=f"{prompt_bundle.system_prompt}\n\n{prompt_bundle.user_prompt}",
                evidence_message_ids=tuple(message.message_id for message in gated.messages),
                max_output_characters=request.policy.maximum_output_characters,
                input_digest=gated.input_digest,
                requested_at=self.clock.now(),
            ),
            bearer_key=bearer_key,
        )
        validated = self._validate_output(
            output=provider_result.output_text,
            gate_messages=gated.messages,
            knowledge=knowledge,
        )
        usage = provider_result.usage or AiUsage(
            input_tokens=0,
            output_tokens=0,
            latency_milliseconds=0,
            estimated_cost_microunits=0,
        )
        return AiGatewayResult(
            findings=validated.findings,
            usage=usage,
            reservation=reservation,
            input_digest=gated.input_digest,
            output_digest=validated.output_digest,
            prompt_version=prompt_bundle.prompt_version,
            rubric_version=prompt_bundle.rubric_version,
            provider_code=request.policy.provider_code.value,
            model_code=provider_result.model_code,
            validated_output_json=validated.canonical_output_json,
            retrieved_knowledge=knowledge,
        )

    def _assemble_messages(
        self,
        *,
        messages: tuple[GatewayMessageInput, ...],
    ) -> AssembledConversationInput:
        assembled_messages: list[SanitizedConversationMessage] = []
        for item in messages:
            if item.content_kind is not EncryptedContentKind.SANITIZED_MESSAGE:
                raise AiGatewayError(failure_code=AiFailureCode.SANITIZATION_MISSING)
            if item.access_purpose is not ContentAccessPurpose.AI_ANALYSIS:
                raise AiGatewayError(failure_code=AiFailureCode.PURPOSE_NOT_ALLOWED)
            assembled_messages.append(
                SanitizedConversationMessage(
                    message_id=item.message_id,
                    sender_role=item.sender_role,
                    sent_at=item.sent_at,
                    sanitized_text=item.sanitized_text,
                )
            )
        return self.assembler.assemble_for_thread(
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            messages=tuple(assembled_messages),
        )

    def _gate_input(
        self,
        *,
        tenant_id: UUID,
        policy: TenantAiPolicy,
        purpose: AiPurpose,
        gate_messages: tuple[GateMessage, ...],
    ) -> AiGateAcceptedInput:
        try:
            return self.input_gate.verify_and_hash(
                tenant_id=tenant_id,
                policy=policy,
                purpose=purpose,
                messages=gate_messages,
            )
        except AiInputGateError as error:
            raise AiGatewayError(failure_code=error.failure_code) from error

    def _validate_output(
        self,
        *,
        output: str,
        gate_messages: tuple[GateMessage, ...],
        knowledge: tuple[KnowledgeRetrievalResult, ...],
    ) -> ValidatedAiOutput:
        allowed_evidence_ids = frozenset(item.message_id for item in gate_messages)
        allowed_knowledge_ids = frozenset(item.chunk_id for item in knowledge)
        try:
            return self.output_validator.validate_conversation_analysis_json(
                output_text=output,
                allowed_evidence_message_ids=allowed_evidence_ids,
                allowed_knowledge_chunk_ids=allowed_knowledge_ids,
            )
        except AiOutputValidationError as error:
            raise AiGatewayError(failure_code=error.failure_code) from error
