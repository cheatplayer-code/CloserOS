# Architecture Decision Record Index

Store individual ADRs under `docs/adr/`.

## ADR template

```markdown
# ADR-XXXX: Title

Status: proposed | accepted | superseded | rejected
Date: YYYY-MM-DD
Decision owners:

## Context

## Decision

## Alternatives considered

## Consequences

## Security and privacy impact

## Migration and rollback/remediation

## Sources verified

Official documentation and verification date.
```

## Current decisions

### ADR-0001 — Modular monolith

Status: accepted
File: `docs/adr/ADR-0001-modular-monolith.md`

Use one modular backend codebase and separate runtime processes for API, worker, and scheduler. Do not introduce microservices until measured scaling or isolation needs justify them.

### ADR-0002 — Provider-neutral AI gateway

Status: accepted
File: `docs/adr/ADR-0002-provider-neutral-ai-gateway.md`

Domain and application layers depend on an internal AI interface. DeepSeek is an initial adapter, not a permanent architectural dependency.

### ADR-0003 — Observer mode first

Status: accepted
File: `docs/adr/ADR-0003-observer-mode-first.md`

The first paid release observes existing bots/managers and produces tasks and analysis. It does not autonomously send messages.

### ADR-0004 — CRM outcome authority

Status: accepted
File: `docs/adr/ADR-0004-crm-outcome-authority.md`

Final won/lost outcomes originate from CRM or explicit authorized human input, never from LLM inference alone.

### ADR-0005 — External AI receives sanitized text only

Status: accepted
File: `docs/adr/ADR-0005-sanitized-only-external-ai.md`

Raw personal and restricted data stays outside external LLM providers. Uncertain redaction fails closed.

### ADR-0006 — Transactional outbox

Status: accepted
File: `docs/adr/ADR-0006-transactional-outbox.md`

Persist an outbox job in the same PostgreSQL transaction as every accepted webhook event or state change that requires asynchronous processing.

### ADR-0007 — ConversationThread and SalesCase

Status: accepted
File: `docs/adr/ADR-0007-conversation-thread-and-sales-case.md`

A ConversationThread is one provider-specific conversation. An optional SalesCase groups related threads, identities, and CRM deals without merging source histories.

### ADR-0008 — uv and pnpm monorepo tooling

Status: accepted
File: `docs/adr/ADR-0008-uv-pnpm-monorepo-tooling.md`

Use `uv` for the Python workspace, `pnpm` through Corepack for JavaScript, and root pnpm scripts for cross-workspace task execution.

### ADR-0009 — Pydantic and OpenAPI contract direction

Status: accepted
File: `docs/adr/ADR-0009-pydantic-openapi-contracts.md`

Define initial backend contracts with Pydantic and expose them through OpenAPI. TypeScript client generation requires a later ADR and task.

### ADR-0010 — Authentication and session strategy

Status: accepted
File: `docs/adr/ADR-0010-authentication-and-session-strategy.md`

CloserOS uses self-hosted authentication with server-side opaque sessions, Argon2id password hashing, secure cookies, verification and reset token hashes, and MFA for privileged roles.

### ADR-0011 — Immutable audit log subsystem

Status: accepted
File: `docs/adr/ADR-0011-immutable-audit-log-subsystem.md`

Security-sensitive actions append immutable, tenant-aware audit events with allowlisted metadata, database-level update/delete protection, and server-generated request correlation IDs.

### ADR-0012 — Envelope encryption and transactional outbox foundation

Status: accepted
File: `docs/adr/ADR-0012-envelope-encryption-and-transactional-outbox.md`

AES-256-GCM envelope encryption with per-content DEKs, AAD binding, and a `KeyProvider` KMS boundary stores ciphertext in PostgreSQL. The transactional outbox publishes job UUIDs only with at-least-once semantics, lease-based claims, retry/dead-letter handling, and PostgreSQL as the source of truth.

### ADR-0013 — Provider ingestion pipeline and controlled CSV import

Status: accepted
File: `docs/adr/ADR-0013-ingestion-pipeline-and-csv-import.md`

Provider-neutral webhook acceptance with encrypted payload persistence, Redis Streams delivery of outbox job UUIDs only, asynchronous normalization via `webhook.normalize`, and controlled encrypted CSV import with resumable row processing and lawful-source confirmation.

### ADR-0014 — Deterministic local redaction and content-independent metrics

Status: accepted
File: `docs/adr/ADR-0014-deterministic-redaction-and-metrics.md`

Stdlib-only detector and placeholder sanitizer with fail-closed post-scan, encrypted sanitized persistence, idempotent `content.redact` handling, and metadata-only deterministic metrics (`lm-metrics-v1`) with versioned snapshots and `metrics.recalculate` jobs.

### ADR-0015 — Governed AI gateway and tenant-isolated knowledge retrieval

Status: accepted
File: `docs/adr/ADR-0015-governed-ai-gateway-and-knowledge-retrieval.md`

NOPQ introduces a fail-closed AI gateway with strict input/output governance, synthetic-first provider testing, tenant-scoped lexical knowledge indexing/retrieval, and migration baseline `e3b7c9d1f5a2` for AI policy/analysis/knowledge persistence.

### ADR-0017 — Production operations and staging architecture

Status: accepted
File: `docs/adr/ADR-0017-production-operations-and-staging-architecture.md`

Block XY documents staging topology (Vercel web, Railway API/worker/Redis, Supabase
PostgreSQL), remote-only container builds, CI supply-chain scanning, and operational
runbooks without claiming Block Z release-gate completion.
