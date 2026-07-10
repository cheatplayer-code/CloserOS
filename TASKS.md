# Implementation Tasks

Execute tasks in order unless an accepted ADR changes the sequence.

Each task is complete only when its acceptance criteria and applicable items in `docs/DEFINITION_OF_DONE.md` pass.

## P0 — Repository foundation

### CLS-001: Initialize monorepo

Create:

```text
apps/web
apps/api
apps/worker
packages/backend
packages/contracts
packages/ui
infra/docker
docs/adr
tests
```

Acceptance criteria:
- Git repository initialized.
- Root task runner documented.
- Python and Node versions pinned.
- Dependency lockfiles committed.
- Basic formatting, linting, and type-check commands work.
- No application feature code yet.

### CLS-002: Local development environment

Acceptance criteria:
- Docker Compose starts PostgreSQL and Redis.
- Health checks are configured.
- No default passwords are suitable for production.
- `.env.example` documents every variable without secrets.
- Setup works from a clean checkout.

### CLS-003: CI quality gate

Acceptance criteria:
- Formatting, linting, type checks, and tests run in CI.
- Dependency and secret scanning are enabled.
- Pull requests fail on quality errors.
- Paid external APIs are never called.

## P1 — Identity, tenancy, and audit foundation

### CLS-010: Tenant and user domain

Implement:
- tenant;
- user;
- membership;
- role;
- invitation;
- account status.

Acceptance criteria:
- Owner, Sales Head, Manager, Analyst, Compliance Admin roles exist.
- Server-side authorization tests cover cross-tenant access denial.
- Tenant suspension blocks access safely.

### CLS-011: Authentication

Acceptance criteria:
- Secure session strategy documented.
- Passwords use a modern adaptive hash if password login is used.
- Email verification and reset flows are designed.
- MFA is required for privileged roles before first commercial onboarding.

### CLS-012: Audit log

Acceptance criteria:
- Security-sensitive actions create immutable audit records.
- Message bodies and secrets are excluded.
- Audit events include actor, tenant, action, target, timestamp, and request correlation ID.

## P2 — Canonical conversation platform

### CLS-020: Canonical schemas

Implement versioned schemas for:
- channel connection;
- lead;
- conversation thread;
- sales case;
- message;
- message edit, deletion, and delivery-status events;
- manager assignment;
- CRM outcome;
- webhook event.

Acceptance criteria:
- Provider-specific fields remain in adapter metadata.
- Contract tests validate backward compatibility.
- All tenant-owned records include `tenant_id`.
- A `ConversationThread` belongs to one provider connection and external conversation.
- A `SalesCase` may group multiple threads, identities, and CRM deals without merging their source histories.
- Original messages are immutable; current message state is a derived projection of immutable events.

### CLS-021: Ingestion pipeline

Acceptance criteria:
- Idempotent event ingestion.
- Fast acknowledgement path.
- Asynchronous processing.
- The webhook event and outbox job are persisted in one PostgreSQL transaction before acknowledgement.
- Workers publish or claim persisted outbox jobs without carrying raw content in the queue.
- Unpublished and timed-out outbox jobs are recoverable after process or queue failure.
- Retry and dead-letter behavior.
- Correlation IDs.
- Reconciliation job interface.

### CLS-022: Encrypted message storage

Acceptance criteria:
- Raw content and sanitized content are stored separately.
- Raw content is encrypted at rest.
- Key rotation approach is documented.
- Logs contain no message body.

### CLS-023: Controlled CSV import

Dependencies:
- CLS-020 canonical schemas;
- CLS-021 ingestion pipeline;
- CLS-022 encrypted storage.

Acceptance criteria:
- Tenant-scoped schema preview and explicit column mapping are required before import.
- The tenant confirms the lawful source and approved purpose of the data.
- File size, content type, and allowed schema are validated before processing.
- Files are malware-scanned and processed from encrypted temporary storage.
- Import processing is asynchronous, idempotent, resumable, and produces a row-level error report without exposing unrelated personal data.
- Imported records use the same canonical validation and tenant-isolation rules as provider events.
- Temporary files and failed imports follow the configured retention and deletion policy.
- Tests use synthetic data only and do not call external services by default.

## P3 — Privacy and AI foundation

### CLS-030: PII and sensitive-data detector

Acceptance criteria:
- Detects configured identifiers.
- Produces stable placeholders.
- Blocks prohibited sensitive categories.
- Includes adversarial and false-negative tests.
- Records detector version.

### CLS-031: Deterministic metrics engine

Initial metrics:
- first response time;
- median response time;
- unanswered conversation thread;
- last sender;
- SLA breach;
- follow-up due/overdue;
- question coverage where deterministically measurable.

Acceptance criteria:
- Time-zone handling is explicit.
- Business hours are tenant-configurable.
- Tests cover ordering, duplicates, edits, and missing timestamps.

### CLS-032: AI provider gateway

Acceptance criteria:
- Provider-neutral interface.
- DeepSeek adapter isolated in infrastructure layer.
- Structured output validation.
- Timeouts, retry budget, circuit breaker, and cost tracking.
- Sanitized input only.
- No paid calls in tests.

### CLS-033: Evidence-backed conversation analysis

Acceptance criteria:
- Controlled issue taxonomy.
- Evidence message IDs must exist.
- Prompt and rubric versions stored.
- Low-confidence findings require review.
- Human accept/reject/correct feedback stored.

### CLS-034: Knowledge-base ingestion

Dependencies:
- CLS-010 tenant and user domain;
- CLS-012 audit log;
- CLS-022 encrypted storage;
- CLS-030 sensitive-data detector.

Acceptance criteria:
- Knowledge documents and every version are tenant-scoped.
- Upload size, content type, and approved file formats are validated.
- Files are malware-scanned and parsed in an isolated, resource-limited process.
- Documents record source, version, effective dates, approval status, and retention state.
- Unapproved, expired, deleted, or quarantined content cannot be used for recommendations.
- Approval, replacement, quarantine, and deletion actions are audited without logging document content.
- Tests cover malicious files, parser failure, tenant isolation, versioning, and deletion using synthetic fixtures.

### CLS-035: Tenant-isolated knowledge retrieval

Dependencies:
- CLS-034 knowledge-base ingestion;
- CLS-032 AI provider gateway.

Acceptance criteria:
- Retrieval is always scoped to one authenticated tenant and an explicit approved purpose.
- Only approved and currently effective document versions are eligible.
- Retrieved passages preserve document and version identifiers for citations.
- No cross-tenant index, cache key, query, or retrieval result is permitted.
- Customer and document instructions are treated as untrusted content, not as system instructions.
- Sanitized text remains potentially pseudonymized personal data and follows the external-AI policy gate.
- Tests cover cross-tenant denial, stale versions, deleted documents, prompt injection, and citation integrity.

## P4 — First useful product surface

### CLS-040: Owner dashboard

Acceptance criteria:
- New, answered, qualified, won, lost, unresolved, and follow-up counts.
- Data freshness displayed.
- Aggregates drill down to evidence.
- No unsupported “lost revenue” claims.
- Before a CRM is connected, CRM-dependent metrics display `unavailable`.
- When CRM synchronization is outside its freshness policy, CRM-dependent metrics display `stale` and the last successful sync time.
- AI must never infer factual qualified, won, or lost counts.

### CLS-041: Conversation review

Acceptance criteria:
- ConversationThread timeline view with optional SalesCase context.
- Deterministic metrics.
- AI findings with evidence.
- Human review controls.
- Authorized PII reveal is audited.

### CLS-042: Manager scorecards

Acceptance criteria:
- Process and outcome scores remain separate.
- Formula and sample size visible.
- No single opaque score.
- Comparison filters avoid misleading cross-team comparisons.

### CLS-043: Follow-up task queue

Acceptance criteria:
- Due date and reason.
- Link to evidence.
- Suggested text clearly labeled as AI.
- Business-fact suggestions cite approved tenant knowledge when such facts are used.
- No automatic outbound send.

## P5 — First official messaging integration

### CLS-050: Select provider

Decision gate:
- Choose based on design-partner demand.
- Verify official API, business eligibility, app review, data access, costs, and webhook model.
- Record ADR.

### CLS-051: Provider sandbox connection

Acceptance criteria:
- OAuth/token lifecycle.
- Signature verification.
- Idempotent incoming messages and statuses.
- Connection health.
- Token revocation.
- Sandbox integration tests.

### CLS-052: Production onboarding workflow

Acceptance criteria:
- Customer authorization flow.
- Least-privilege scopes.
- Legal notices and responsibilities displayed.
- Connection state machine.
- Recovery from expired/revoked credentials.

## P6 — CRM outcomes

### CLS-060: CRM adapter contract

Acceptance criteria:
- Lead/deal mapping.
- Owner, stage, amount, currency, outcome, reason.
- Webhook and reconciliation interface.
- CRM remains source of truth for outcomes.

### CLS-061: First CRM integration

Select from actual design-partner stack.

Acceptance criteria:
- Official API only.
- Incremental sync.
- Retry/reconciliation.
- Conflicts surfaced, not silently overwritten.

### CLS-062: Revenue-at-risk model

Acceptance criteria:
- Uses stage-level historical conversion and configured value basis.
- Shows low/base/high range.
- Shows assumptions.
- Falls back to “opportunities at risk” when data is insufficient.

## P7 — Production hardening and paid pilot

### CLS-070: Kazakhstan deployment

Acceptance criteria:
- Approved jurisdiction and provider documented.
- PostgreSQL, object storage, backups, and logs stay in approved locations.
- TLS, secrets management, monitoring, and alerting enabled.
- Restore test completed.

### CLS-071: Privacy operations

Acceptance criteria:
- Retention schedules.
- Tenant deletion.
- Data-subject request workflow.
- Export controls.
- Subprocessor registry.
- Incident response runbook.

### CLS-072: Paid design-partner onboarding

Acceptance criteria:
- Signed commercial agreement and DPA.
- Business confirms lawful data access and notices.
- One official channel connected.
- Baseline period defined.
- Success metrics agreed before analysis.
- Pilot payment received.

### CLS-073: Production release gate

All applicable checks in `docs/DEFINITION_OF_DONE.md` must pass.

## Later phases — not authorized yet

- Unified outbound inbox.
- Pre-send live coach.
- Instagram as a second channel.
- Telegram Business as a second or third channel.
- Autonomous follow-up.
- Recovery campaigns.
- Fine-tuning.
- Cross-tenant benchmarks.
- Microservices.
