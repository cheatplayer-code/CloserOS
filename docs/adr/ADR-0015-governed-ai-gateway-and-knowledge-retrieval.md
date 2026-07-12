# ADR-0015: Governed AI gateway and tenant-isolated knowledge retrieval

Status: Accepted
Date: 2026-07-12
Decision owners: CloserOS owners

## Context

Block LM delivered deterministic redaction and metrics but intentionally left
`message.analyze` unimplemented. Block NOPQ requires:

- a provider-neutral AI gateway with fail-closed policy enforcement;
- strict structured output validation with evidence and citation integrity;
- tenant-isolated lexical knowledge retrieval over encrypted chunks;
- deterministic local/offline test behavior with no paid model calls in CI.

The implementation must preserve ADR-0004 and ADR-0005 constraints:

- CRM remains factual outcome authority;
- external providers receive sanitized text only.

## Decision

### Governed AI gateway contract

Implement `AiGateway` in the application layer as the only orchestration path for
conversation analysis. The gateway:

- accepts `AiGatewayRequest` with explicit tenant, purpose, model, budget, and
  sanitized message envelope;
- rejects non-analysis purposes for this phase;
- enforces `AI_EXTERNAL_CALLS_ENABLED` fail-closed behavior;
- validates content kind and purpose (`SANITIZED_MESSAGE` +
  `ContentAccessPurpose.AI_ANALYSIS`) before provider calls;
- executes deterministic sequence:
  1. assemble transcript;
  2. gate and hash input;
  3. reserve budget;
  4. retrieve tenant-scoped knowledge;
  5. build versioned prompt;
  6. call provider through neutral port;
  7. validate strict output.

### Input governance

`AiInputGate` is mandatory before provider calls:

- tenant/purpose policy checks;
- message-count and character limits;
- eligibility check (`AnalysisEligibility.ELIGIBLE` only);
- residual sensitive-data scan over sanitized text;
- deterministic input digest generation.

Any failure maps to a controlled `AiFailureCode`.

### Output governance

`AiOutputValidator` enforces strict JSON schema and safety:

- exact allowed top-level and finding keys;
- controlled issue/severity taxonomy;
- bounded explanation and recommended-action text;
- evidence IDs must exist in supplied conversation context;
- citation chunk IDs must exist in supplied retrieval context;
- chain-of-thought field rejection at any nesting level;
- residual sensitive-data rejection in all validated payload text.

### Provider adapters

Use provider-neutral ports (`AiProvider`, registry, credential resolver, clock).
Two adapters are part of NOPQ:

- `OpenAICompatibleChatAdapter`: HTTPS-only base URL, bounded response bytes and
  characters, deterministic timeout settings, no SDK dependency;
- `SyntheticAiProvider`: deterministic JSON output for local/CI tests.

### Knowledge retrieval

Implement tenant-isolated lexical retrieval:

- deterministic chunking with overlap;
- keyed HMAC term digests (`knowledge_chunk_terms`) per tenant search key;
- ranked search over active/indexed versions only;
- decrypt chunk ciphertext with
  `ContentAccessPurpose.KNOWLEDGE_RETRIEVAL`;
- append `knowledge.retrieval.completed` audit events.

### Knowledge indexing workflow

Implement `knowledge.index` outbox handler:

- accepts `knowledge_document_version` references only;
- requires approved version state;
- decrypts UTF-8 `knowledge_document` content;
- chunks, encrypts chunk plaintext as `knowledge_chunk`;
- writes lexical term index rows;
- marks version indexed;
- appends `knowledge.version.indexed` audit event;
- maps failures to typed outbox error codes.

### Schema baseline

Adopt Alembic revision `e3b7c9d1f5a2` as migration head for NOPQ:

- `tenant_ai_policies`, `ai_usage_daily`;
- knowledge tables;
- conversation analysis tables;
- extended `encrypted_contents` and `audit_events` CHECK constraints.

## Alternatives considered

- **Direct provider calls from handlers/routes** — rejected; bypasses uniform
  policy, budget, and validation controls.
- **Vector-only retrieval in NOPQ** — rejected; increases dependency/risk before
  deterministic lexical baseline is proven.
- **Permissive schema validation with best-effort parsing** — rejected; weakens
  auditability and introduces silent hallucination risk.

## Consequences

- NOPQ can run fully offline in tests using synthetic provider fixtures.
- `message.analyze` worker handler is still not wired in this phase; gateway and
  validation primitives exist and are tested.
- Knowledge retrieval quality starts as lexical baseline; semantic retrieval
  remains future work.

## Security and privacy impact

- external AI input remains sanitized-only and fail-closed;
- knowledge retrieval and decryption are tenant-scoped and audited;
- no message body, token, or credential logging is introduced;
- test fixtures use synthetic sanitized data only.

## Migration and rollback/remediation

- upgrade to `e3b7c9d1f5a2` for NOPQ schema objects;
- downgrade restores LM constraints and drops NOPQ tables; safe only for empty or
  isolated test databases;
- production remediation follows expand/migrate/contract with archival policy.

## Sources verified

- `AGENTS.md`, `docs/SECURITY_COMPLIANCE.md`, ADR-0005, ADR-0012, ADR-0014;
- implementation modules under `packages/backend/src/closeros/application` and
  `packages/backend/src/closeros/infrastructure`;
- migration `e3b7c9d1f5a2_nopq_ai_knowledge.py`.

