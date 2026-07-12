# AI Gateway (NOPQ)

This document describes the NOPQ application-layer AI gateway contract and
operational constraints.

## Scope

The current gateway supports `conversation.analysis` only.

Implemented modules:

- `ai_gateway.py`
- `ai_input_gate.py`
- `ai_output_validator.py`
- `ai_prompt_builder.py`
- `ai_budget_service.py`
- `ai_ports.py`
- `openai_compatible_adapter.py`
- `synthetic_ai_provider.py`

## Mandatory execution flow

1. Validate purpose (`conversation.analysis`) and external-call gate.
2. Assemble deterministic transcript from sanitized messages.
3. Run input gate (policy, eligibility, residual-safety scan, digest).
4. Reserve tenant budget.
5. Retrieve tenant-scoped knowledge snippets.
6. Build versioned prompt/rubric bundle.
7. Resolve provider credentials.
8. Call provider through neutral port.
9. Validate strict JSON output and evidence/citation integrity.
10. Return validated findings with digests, usage, versions, and citations.

## Fail-closed behavior

The gateway must fail with controlled `AiFailureCode` values for:

- policy disabled or purpose not allowed;
- sanitization missing/blocked;
- input too large;
- budget exceeded;
- external calls disabled;
- provider unavailable;
- invalid or unsafe provider output.

No best-effort fallback is allowed for unsafe/invalid output.

## Provider policy

- Tests and CI use `SyntheticAiProvider` only.
- `AI_EXTERNAL_CALLS_ENABLED=false` remains default in test environments.
- No live paid AI calls are allowed in default test execution.

## Data-handling constraints

- External providers receive sanitized text only.
- Evidence IDs in output must map to analyzed message IDs.
- Knowledge citations must map to retrieved chunk IDs.
- Chain-of-thought keys are rejected.
- Output text is scanned for sensitive-data leakage before acceptance.

## Observability and audit metadata

Persist/emit metadata only:

- provider/model code;
- prompt/rubric version;
- input/output digests;
- token usage and latency;
- validation status;
- failure code when rejected.

Never log raw prompts, message bodies, or provider credentials.

