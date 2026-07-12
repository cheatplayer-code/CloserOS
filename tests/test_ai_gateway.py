"""Unit tests for AI gateway orchestration."""

# mypy: disable-error-code=arg-type

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from closeros.application.ai_budget_service import AiBudgetService
from closeros.application.ai_gateway import (
    AiGateway,
    AiGatewayError,
    AiGatewayRequest,
    GatewayMessageInput,
)
from closeros.application.ai_input_gate import AiInputGate
from closeros.application.ai_output_validator import AiOutputValidator
from closeros.application.ai_ports import (
    AiProvider,
    AiProviderRegistry,
    ProviderRequest,
    ProviderResult,
)
from closeros.application.ai_prompt_builder import AiPromptBuilder
from closeros.application.conversation_input_assembler import ConversationInputAssembler
from closeros.domain.ai_analysis import (
    AiBudget,
    AiFailureCode,
    AiProviderCode,
    AiPurpose,
    AiUsage,
    TenantAiPolicy,
)
from closeros.domain.encrypted_content import ContentAccessPurpose, EncryptedContentKind
from closeros.domain.knowledge import KnowledgeDocumentKind, KnowledgeRetrievalResult


def _now() -> datetime:
    return datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def _policy(tenant_id: UUID) -> TenantAiPolicy:
    now = _now()
    return TenantAiPolicy(
        tenant_id=tenant_id,
        enabled=True,
        provider_code=AiProviderCode.SYNTHETIC,
        allowed_purposes=frozenset({AiPurpose.CONVERSATION_ANALYSIS}),
        processing_region_code="kz",
        prompt_version="nopq-prompt-v1",
        rubric_version="nopq-rubric-v1",
        maximum_messages_per_request=32,
        maximum_sanitized_characters=8_000,
        maximum_output_characters=4_000,
        daily_input_token_budget=5_000,
        daily_output_token_budget=5_000,
        daily_cost_budget_microunits=100_000,
        maximum_retrieved_knowledge_chunks=4,
        created_at=now,
        updated_at=now,
        version=1,
    )


def _budget() -> AiBudget:
    return AiBudget(
        daily_input_token_budget=5_000,
        daily_output_token_budget=5_000,
        daily_cost_budget_microunits=100_000,
    )


def _message(message_id: str, text: str) -> GatewayMessageInput:
    return GatewayMessageInput(
        message_id=UUID(message_id),
        sender_role="manager",
        sent_at=_now(),
        content_kind=EncryptedContentKind.SANITIZED_MESSAGE,
        access_purpose=ContentAccessPurpose.AI_ANALYSIS,
        sanitized_text=text,
    )


def _request(
    tenant_id: UUID, *, message_text: str = "Synthetic safe text for analysis."
) -> AiGatewayRequest:
    return AiGatewayRequest(
        tenant_id=tenant_id,
        policy=_policy(tenant_id),
        purpose=AiPurpose.CONVERSATION_ANALYSIS,
        model_code="synthetic-model",
        messages=(_message("00000000-0000-0000-0000-000000000101", message_text),),
        current_budget=_budget(),
        estimated_usage=AiUsage(
            input_tokens=80,
            output_tokens=60,
            latency_milliseconds=0,
            estimated_cost_microunits=1_000,
        ),
    )


@dataclass
class _Clock:
    def now(self) -> datetime:
        return _now()


class _CredentialResolver:
    def __init__(self, token: str | None = "synthetic-token") -> None:
        self._token = token

    async def resolve_bearer_key(self, **_: object) -> str | None:
        return self._token


class _Knowledge:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve_for_conversation(self, **_: object) -> tuple[KnowledgeRetrievalResult, ...]:
        self.calls += 1
        return (
            KnowledgeRetrievalResult(
                chunk_id=UUID("00000000-0000-0000-0000-000000000201"),
                source_code="kb_sales_playbook",
                version_number=1,
                document_kind=KnowledgeDocumentKind.GENERAL_REFERENCE,
                match_weight=100,
                decrypted_text="Always confirm next action and date.",
            ),
        )


class _Provider(AiProvider):
    provider_code = AiProviderCode.SYNTHETIC

    def __init__(self, output_json: dict[str, object] | None = None) -> None:
        self._output_json = output_json or {
            "purpose": "conversation.analysis",
            "findings": [
                {
                    "issue_code": "missing_next_step",
                    "severity": "medium",
                    "confidence_basis_points": 6100,
                    "explanation": "No clear next step is confirmed in the dialog.",
                    "recommended_action": "Confirm owner, date, and follow-up channel.",
                    "evidence_message_ids": ["00000000-0000-0000-0000-000000000101"],
                    "knowledge_citations": [],
                }
            ],
        }

    async def call_chat_json(self, *, request: ProviderRequest, bearer_key: str) -> ProviderResult:
        _ = bearer_key
        return ProviderResult(
            provider_code=request.provider_code,
            model_code=request.model_code,
            purpose=request.purpose,
            output_text=json.dumps(self._output_json),
            usage=AiUsage(
                input_tokens=70,
                output_tokens=50,
                latency_milliseconds=12,
                estimated_cost_microunits=900,
            ),
            completed_at=_now(),
        )


class _Registry(AiProviderRegistry):
    def __init__(self, provider: AiProvider) -> None:
        self._provider = provider

    def get_provider(self, *, provider_code: AiProviderCode) -> AiProvider:
        assert provider_code is AiProviderCode.SYNTHETIC
        return self._provider


def _gateway(
    *,
    external_calls_enabled: bool = True,
    bearer_key: str | None = "synthetic-token",
    provider_output: dict[str, object] | None = None,
) -> AiGateway:
    return AiGateway(
        external_calls_enabled=external_calls_enabled,
        clock=_Clock(),
        input_gate=AiInputGate(),
        assembler=ConversationInputAssembler(),
        prompt_builder=AiPromptBuilder(),
        output_validator=AiOutputValidator(),
        budget_service=AiBudgetService(),
        provider_registry=_Registry(_Provider(provider_output)),
        credential_resolver=_CredentialResolver(bearer_key),
        knowledge_retrieval=_Knowledge(),
    )


def test_gateway_successfully_analyzes_conversation() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        result = await _gateway().analyze_conversation(request=_request(tenant_id))
        assert result.findings
        assert result.reservation.approved is True
        assert result.provider_code == "synthetic"
        assert result.prompt_version == "nopq-prompt-v1"
        assert result.rubric_version == "nopq-rubric-v1"
        assert len(result.input_digest) == 32
        assert len(result.output_digest) == 32

    asyncio.run(exercise())


def test_gateway_rejects_non_analysis_purpose() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        req = _request(tenant_id)
        req = AiGatewayRequest(
            tenant_id=req.tenant_id,
            policy=req.policy,
            purpose=AiPurpose.REPLY_SUGGESTION,
            model_code=req.model_code,
            messages=req.messages,
            current_budget=req.current_budget,
            estimated_usage=req.estimated_usage,
        )
        with pytest.raises(AiGatewayError) as error:
            await _gateway().analyze_conversation(request=req)
        assert error.value.failure_code is AiFailureCode.PURPOSE_NOT_ALLOWED

    asyncio.run(exercise())


def test_gateway_rejects_when_external_calls_are_disabled() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        with pytest.raises(AiGatewayError) as error:
            await _gateway(external_calls_enabled=False).analyze_conversation(
                request=_request(tenant_id)
            )
        assert error.value.failure_code is AiFailureCode.EXTERNAL_CALLS_DISABLED

    asyncio.run(exercise())


def test_gateway_rejects_when_content_is_not_sanitized_kind() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        bad = GatewayMessageInput(
            message_id=UUID("00000000-0000-0000-0000-000000000101"),
            sender_role="manager",
            sent_at=_now(),
            content_kind=EncryptedContentKind.RAW_MESSAGE,
            access_purpose=ContentAccessPurpose.AI_ANALYSIS,
            sanitized_text="safe text",
        )
        req = AiGatewayRequest(
            tenant_id=tenant_id,
            policy=_policy(tenant_id),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            model_code="synthetic-model",
            messages=(bad,),
            current_budget=_budget(),
            estimated_usage=AiUsage(10, 10, 0, 10),
        )
        with pytest.raises(AiGatewayError) as error:
            await _gateway().analyze_conversation(request=req)
        assert error.value.failure_code is AiFailureCode.SANITIZATION_MISSING

    asyncio.run(exercise())


def test_gateway_rejects_when_budget_not_approved() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        req = _request(tenant_id)
        req = AiGatewayRequest(
            tenant_id=req.tenant_id,
            policy=req.policy,
            purpose=req.purpose,
            model_code=req.model_code,
            messages=req.messages,
            current_budget=AiBudget(100, 100, 100),
            estimated_usage=AiUsage(1_000, 1_000, 0, 1_000),
        )
        with pytest.raises(AiGatewayError) as error:
            await _gateway().analyze_conversation(request=req)
        assert error.value.failure_code is AiFailureCode.BUDGET_EXCEEDED

    asyncio.run(exercise())


def test_gateway_rejects_when_provider_credentials_are_missing() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        with pytest.raises(AiGatewayError) as error:
            await _gateway(bearer_key=None).analyze_conversation(request=_request(tenant_id))
        assert error.value.failure_code is AiFailureCode.PROVIDER_UNAVAILABLE

    asyncio.run(exercise())


def test_gateway_maps_output_validator_errors() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        provider_output = {
            "purpose": "conversation.analysis",
            "findings": [
                {
                    "issue_code": "missing_next_step",
                    "severity": "medium",
                    "confidence_basis_points": 6100,
                    "explanation": "Unsafe email leak@example.test",
                    "recommended_action": "Confirm owner and date.",
                    "evidence_message_ids": ["00000000-0000-0000-0000-000000000101"],
                    "knowledge_citations": [],
                }
            ],
        }
        with pytest.raises(AiGatewayError) as error:
            await _gateway(provider_output=provider_output).analyze_conversation(
                request=_request(tenant_id)
            )
        assert error.value.failure_code is AiFailureCode.UNSAFE_OUTPUT

    asyncio.run(exercise())


def test_gateway_rejects_wrong_access_purpose() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        bad = GatewayMessageInput(
            message_id=UUID("00000000-0000-0000-0000-000000000101"),
            sender_role="manager",
            sent_at=_now(),
            content_kind=EncryptedContentKind.SANITIZED_MESSAGE,
            access_purpose=ContentAccessPurpose.REDACTION,
            sanitized_text="safe text",
        )
        req = AiGatewayRequest(
            tenant_id=tenant_id,
            policy=_policy(tenant_id),
            purpose=AiPurpose.CONVERSATION_ANALYSIS,
            model_code="synthetic-model",
            messages=(bad,),
            current_budget=_budget(),
            estimated_usage=AiUsage(10, 10, 0, 10),
        )
        with pytest.raises(AiGatewayError) as error:
            await _gateway().analyze_conversation(request=req)
        assert error.value.failure_code is AiFailureCode.PURPOSE_NOT_ALLOWED

    asyncio.run(exercise())


def test_gateway_maps_validator_invalid_output_to_failure_code() -> None:
    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        provider_output = {"purpose": "conversation.analysis", "findings": [{"bad": "shape"}]}
        with pytest.raises(AiGatewayError) as error:
            await _gateway(provider_output=provider_output).analyze_conversation(
                request=_request(tenant_id)
            )
        assert error.value.failure_code is AiFailureCode.PROVIDER_OUTPUT_INVALID

    asyncio.run(exercise())


def test_gateway_returns_zero_usage_when_provider_usage_missing() -> None:
    class NoUsageProvider(_Provider):
        async def call_chat_json(
            self, *, request: ProviderRequest, bearer_key: str
        ) -> ProviderResult:
            result = await super().call_chat_json(request=request, bearer_key=bearer_key)
            return ProviderResult(
                provider_code=result.provider_code,
                model_code=result.model_code,
                purpose=result.purpose,
                output_text=result.output_text,
                usage=None,
                completed_at=result.completed_at,
            )

    async def exercise() -> None:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        gateway = AiGateway(
            external_calls_enabled=True,
            clock=_Clock(),
            input_gate=AiInputGate(),
            assembler=ConversationInputAssembler(),
            prompt_builder=AiPromptBuilder(),
            output_validator=AiOutputValidator(),
            budget_service=AiBudgetService(),
            provider_registry=_Registry(NoUsageProvider()),
            credential_resolver=_CredentialResolver("synthetic-token"),
            knowledge_retrieval=_Knowledge(),
        )
        result = await gateway.analyze_conversation(request=_request(tenant_id))
        assert result.usage.input_tokens == 0
        assert result.usage.output_tokens == 0
        assert result.usage.estimated_cost_microunits == 0

    asyncio.run(exercise())
