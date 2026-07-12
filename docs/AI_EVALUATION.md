# AI Evaluation (NOPQ)

This document defines the baseline synthetic/offline evaluation approach for
NOPQ AI modules.

## Goals

- Validate governed gateway contracts before wiring production analysis flow.
- Ensure deterministic pass/fail behavior without paid provider calls.
- Detect schema, evidence, citation, and privacy regressions early.

## Test policy

- `AI_EXTERNAL_CALLS_ENABLED=false` in tests by default.
- Use `SyntheticAiProvider` and synthetic sanitized fixtures only.
- Never include real customer data or credentialed production URIs.

## Required evaluation checks

1. **Input gate**: policy, purpose, limits, eligibility, residual-safety scan,
   deterministic digest.
2. **Output validator**: strict schema, taxonomy, evidence IDs, citation IDs,
   chain-of-thought rejection, unsafe-output blocking.
3. **Gateway orchestration**: failure-code mapping, budget behavior, provider-key
   handling, validated success path.
4. **Adapter safety**: HTTPS-only, timeout and size guards, strict parsing.
5. **Knowledge retrieval**: tenant scoping, active/indexed filtering, audited
   decrypt-on-access behavior.

## Synthetic harness

`tests/test_ai_evaluation_harness.py` provides synthetic conversation cases with:

- deterministic transcript inputs;
- known evidence IDs;
- strict validation of synthetic provider output;
- expected issue-code assertions.

The harness is intentionally non-production and does not claim business-model
accuracy. It is a contract/regression gate for governed AI behavior.

## Future expansion (RSTU+)

- Add sanctioned sanitized historical eval dataset;
- measure precision/recall by issue code and language;
- calibrate confidence thresholds with reviewer agreement;
- introduce regression dashboards for prompt/model changes.

