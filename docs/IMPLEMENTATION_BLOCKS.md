# Implementation Blocks

This file is the **canonical implementation sequence** for CloserOS AI after the
repository foundation and identity/audit baseline. Future prompts must not rename,
reorder, or redefine these blocks without an explicit accepted update to this file
and `PROJECT_STATUS.md`.

## Combined block order

1. **FG** — shared persistence foundation + canonical conversation contracts
2. **HI** — encrypted message storage + transactional outbox/job foundation
3. **JK** — generic ingestion pipeline + controlled CSV import
4. **LM** — PII/restricted-content detector + deterministic metrics engine
5. **NOPQ** — AI gateway + evidence-backed analysis + knowledge-base ingestion and retrieval
6. **RSTU** — owner dashboard + conversation review + manager scorecards + follow-up task queue
7. **VW** — design-partner/provider decision package + first official messaging provider
8. **XY** — first CRM integration + production hardening
9. **Z** — compliance, security release gate and paid production pilot

**Roadmap consolidation (accepted):** future execution order after LM is
**LM → NOPQ → RSTU → VW → XY → Z**. Blocks NO/PQ and RS/TU are merged into NOPQ
and RSTU respectively; do not split or reorder them without an explicit accepted
update to this file and `PROJECT_STATUS.md`.

## Block FG scope (completed locally)

- Shared SQLAlchemy base, engine/session, unit-of-work, cursor pagination, and
  tenant-scoped repository helpers.
- Persistent tenants, memberships, invitations with normalized roles.
- Authoritative tenant context resolution and tenant listing API.
- Canonical conversation domain v1, versioned cross-language contracts, PostgreSQL
  schema, repositories, immutable message events, and deterministic projection.
- Tenant-scoped audit query HTTP route.
- Migration revision `d4e8f1a2b3c5` chained from audit revision `8e4b1d0f6a23`.

## Block HI scope (completed locally)

- AES-256-GCM envelope encryption with per-content DEKs, AAD binding, and
  `KeyProvider` / `DataKeyCryptography` ports.
- `encrypted_contents` table with tenant-scoped composite foreign keys from
  canonical message and webhook tables.
- `ContentEncryptionService` with purpose-gated decrypt and audited rewrap.
- Atomic commands persisting encrypted content, canonical rows, outbox jobs, and
  audit events in one transaction.
- Transactional outbox domain, `outbox_jobs` / `outbox_job_attempts` persistence,
  publisher/processor/reconciliation services, and queue-ID-only publication port.
- Alembic revision `e7a1c3d5f9b2`; ADR-0012, `docs/ENCRYPTED_CONTENT.md`, and
  `docs/OUTBOX.md`.
- No provider ingestion orchestration, production KMS adapter, or concrete queue
  worker wiring yet.

## Block JK scope (completed locally)

- Provider-neutral adapter ports, registry, and synthetic HMAC adapter (dev/test only).
- Secure webhook HTTP endpoint with atomic encrypted-payload acceptance.
- Real `webhook.normalize` and `csv.import` outbox handlers.
- Redis Streams queue adapter (job UUID only) and worker CLI entry points.
- Controlled encrypted CSV import API with lawful-source confirmation.
- Resumable 250-row CSV processing with safe row-error codes.
- Alembic revision `f2a8c4e6b1d3`; ADR-0013, `docs/INGESTION.md`, and
  `docs/CSV_IMPORT.md`.
- No official messaging provider integration, PII redaction, or production KMS/scanner
  adapters yet.

## Block LM scope (completed locally)

- Stdlib-only deterministic detector (`lm-detector-v1`) and sanitizer
  (`lm-policy-v1`) with fail-closed post-redaction scan.
- Real `content.redact` handler for `message` and `message_edit_event` with
  encrypted sanitized persistence and audit events.
- Content-independent `MetricsEngine` (`lm-metrics-v1`), snapshot persistence,
  `metrics.recalculate` handler, and privileged metrics HTTP routes.
- Alembic revision `d1f3a5c7e9b2`; ADR-0014, `docs/PRIVACY_REDACTION.md`, and
  `docs/METRICS.md`.
- Worker job kinds extended: `content.redact`, `metrics.recalculate`.
- No external AI gateway, `message.analyze` handler, name/address NER, or
  production DLP/scanner adapters yet.

## Block NOPQ scope (implemented locally; PR verification pending)

- Provider-neutral AI application ports with hidden-repr request/response payloads.
- Governed `AiGateway` orchestration with fail-closed purpose, sanitization,
  budget, and output-validation checks.
- Deterministic conversation input assembler and versioned prompt/rubric builder.
- Strict AI output validator:
  - controlled issue/severity taxonomy;
  - evidence-message integrity;
  - knowledge-citation integrity;
  - chain-of-thought key rejection;
  - residual sensitive-data blocking on explanation/action text only.
- OpenAI-compatible adapter with HTTPS-only base URL and bounded response
  parsing; synthetic deterministic provider for local/CI.
- Tenant AI policy/usage persistence, budget reservation, and policy HTTP API.
- Knowledge domain persistence, SQLAlchemy repositories, and integrated unit-of-work
  wiring for knowledge documents, versions, chunks, and lexical terms.
- `knowledge.index` and `message.analyze` outbox handlers with idempotent flows.
- Tenant-scoped knowledge ingestion/approval/revocation and analysis query/request APIs.
- Worker runtime registration for `knowledge.index` and `message.analyze`.
- Alembic revision `e3b7c9d1f5a2` for AI policy/usage, analysis runs/findings, and
  knowledge retrieval schema.

Next block: **RSTU** — owner dashboard, conversation review, manager scorecards,
and follow-up task queue.

## Rules

- Each block builds on prior merged work; do not skip ahead without an ADR.
- Do not implement autonomous outbound messaging in any block before explicit
  product authorization and release-gate approval.
- Raw personal data must not be sent to external LLMs in any block.
- PostgreSQL remains the source of truth; Redis is not a source of truth.
