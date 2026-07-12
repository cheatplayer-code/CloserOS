"""Versioned deterministic prompt and rubric builders for conversation analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from closeros.domain.ai_analysis import (
    MAX_FINDINGS_PER_RUN,
    PROMPT_VERSION,
    RUBRIC_VERSION,
    FindingIssueCode,
)
from closeros.domain.knowledge import KnowledgeRetrievalResult


def _validate_non_empty_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


@dataclass(frozen=True, slots=True)
class PromptBundle:
    prompt_version: str
    rubric_version: str
    system_prompt: str = field(repr=False)
    user_prompt: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prompt_version",
            _validate_non_empty_text(self.prompt_version, "prompt_version"),
        )
        object.__setattr__(
            self,
            "rubric_version",
            _validate_non_empty_text(self.rubric_version, "rubric_version"),
        )
        object.__setattr__(
            self,
            "system_prompt",
            _validate_non_empty_text(self.system_prompt, "system_prompt"),
        )
        object.__setattr__(
            self, "user_prompt", _validate_non_empty_text(self.user_prompt, "user_prompt")
        )


class AiPromptBuilder:
    def build_conversation_analysis_prompt(
        self,
        *,
        sanitized_transcript: str,
        knowledge_results: tuple[KnowledgeRetrievalResult, ...],
        prompt_version: str = PROMPT_VERSION,
        rubric_version: str = RUBRIC_VERSION,
    ) -> PromptBundle:
        transcript = _validate_non_empty_text(sanitized_transcript, "sanitized_transcript")
        if not isinstance(knowledge_results, tuple):
            raise TypeError("knowledge_results must be a tuple")
        if not all(isinstance(item, KnowledgeRetrievalResult) for item in knowledge_results):
            raise TypeError("knowledge_results must contain KnowledgeRetrievalResult values")

        issue_codes = ", ".join(sorted(code.value for code in FindingIssueCode))
        sorted_knowledge = tuple(
            sorted(
                knowledge_results,
                key=lambda item: (
                    item.source_code,
                    item.version_number,
                    str(item.chunk_id),
                ),
            )
        )
        knowledge_lines = [
            (
                f"- chunk_id={item.chunk_id};"
                f" source_code={item.source_code};"
                f" version_number={item.version_number};"
                f" document_kind={item.document_kind.value};"
                f" text={item.decrypted_text}"
            )
            for item in sorted_knowledge
        ]
        knowledge_block = "\n".join(knowledge_lines) if knowledge_lines else "- none"
        system_prompt = (
            "You are an evidence-grounded reviewer for sales conversations.\n"
            "Return strict JSON only. Do not include markdown or prose outside JSON.\n"
            "Do not output chain-of-thought, reasoning traces, or hidden deliberation.\n"
            "Use only allowed issue codes and cite message IDs from the transcript."
        )
        user_prompt = (
            f"Prompt version: {prompt_version}\n"
            f"Rubric version: {rubric_version}\n"
            f"Maximum findings: {MAX_FINDINGS_PER_RUN}\n"
            f"Allowed issue codes: {issue_codes}\n\n"
            "Output schema (JSON object):\n"
            "{\n"
            '  "purpose": "conversation.analysis",\n'
            '  "findings": [\n'
            "    {\n"
            '      "issue_code": "string",\n'
            '      "severity": "low|medium|high|critical",\n'
            '      "confidence_basis_points": 0..10000,\n'
            '      "explanation": "string <= 512 chars",\n'
            '      "recommended_action": "string <= 512 chars",\n'
            '      "evidence_message_ids": ["uuid", "..."],\n'
            '      "knowledge_citations": ['
            '{"chunk_id":"uuid","source_code":"string","version_number":1}'
            "]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Approved knowledge snippets:\n{knowledge_block}\n\n"
            f"Sanitized transcript:\n{transcript}\n"
        )
        return PromptBundle(
            prompt_version=prompt_version,
            rubric_version=rubric_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
