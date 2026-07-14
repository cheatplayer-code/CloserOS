"""Optional live DeepSeek smoke test for reply.suggestion (requires credentials)."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from closeros.application.ai_ports import ProviderRequest
from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
from closeros.application.reply_suggestion_prompt import build_reply_suggestion_prompt
from closeros.application.reply_suggestion_validator import validate_reply_suggestion_json
from closeros.domain.ai_analysis import AiProviderCode, AiPurpose
from closeros.domain.reply_suggestion import REPLY_PROMPT_VERSION, REPLY_RUBRIC_VERSION

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY is not configured",
)


def test_live_deepseek_reply_suggestion_smoke() -> None:
    evidence = uuid4()
    bundle = build_reply_suggestion_prompt(
        sanitized_messages=((evidence, "Здравствуйте, интересует диван до 500000 тенге.")),
        memory_facts=(),
        product_hits=(),
        allowed_commercial_actions=("quote_list_price",),
        playbook_snippets=(),
    )
    adapter = OpenAICompatibleChatAdapter(
        base_url="https://api.deepseek.com",
        provider_code=AiProviderCode.OPENAI_COMPATIBLE,
    )
    request = ProviderRequest(
        tenant_id=uuid4(),
        provider_code=AiProviderCode.OPENAI_COMPATIBLE,
        purpose=AiPurpose.REPLY_SUGGESTION,
        model_code="deepseek-chat",
        prompt_version=REPLY_PROMPT_VERSION,
        rubric_version=REPLY_RUBRIC_VERSION,
        prompt_text=f"{bundle.system_prompt}\n\n{bundle.user_prompt}",
        evidence_message_ids=(evidence,),
    )
    result = asyncio.run(
        adapter.call_chat_json(
            request=request,
            bearer_key=os.environ["DEEPSEEK_API_KEY"],
        )
    )
    payload = json.loads(result.output_text)
    assert payload.get("purpose") == AiPurpose.REPLY_SUGGESTION.value
    validate_reply_suggestion_json(
        raw_text=result.output_text,
        allowed_evidence_message_ids=frozenset({evidence}),
        allowed_product_variant_ids=frozenset(),
        allowed_knowledge_chunk_ids=frozenset(),
    )
