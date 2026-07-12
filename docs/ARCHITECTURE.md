# Architecture

## 1. Architectural style

Use a modular monolith with asynchronous workers.

Reasons:
- small team;
- limited budget;
- need for clear transactional boundaries;
- easier local development;
- lower deployment complexity;
- enough separation for future extraction if scale proves it necessary.

Do not split by channel into independent services.

## 2. System context

```text
Messaging providers ─┐
CRM providers ────────┼─> Integration adapters
CSV imports ──────────┘          |
                                  v
                           Ingestion API
                                  |
               verify -> dedupe -> persist event + outbox
                                  |
                                  v
                    Transactional outbox publisher
                                  |
                                  v
                         Background job queue
                       /          |            \
                 redaction    metrics       CRM linking
                       \          |            /
                                  v
                           AI analysis gateway
                                  |
                                  v
                     findings / tasks / scorecards
                                  |
                     web app / reports / alerts
```

## 3. Repository structure

```text
apps/
  web/
  api/
  worker/
packages/
  backend/
  contracts/
  ui/
infra/
  docker/
  migrations/
docs/
  adr/
tests/
```

## 4. Backend modules

Suggested modules:

```text
identity
tenancy
audit
connections
ingestion
conversations
crm
privacy
metrics
ai
findings
followups
knowledge
reporting
billing
operations
```

Each module owns:
- domain models;
- application use cases;
- repository interfaces;
- API contracts;
- tests.

Shared utilities must remain small. Avoid a generic `utils` dumping ground.

## 5. Request boundaries

### Synchronous API

Use for:
- authentication;
- dashboard reads;
- review actions;
- configuration;
- connection setup;
- lightweight commands.

### Asynchronous jobs

Use for:
- webhook processing after acknowledgement;
- redaction;
- message analysis;
- report generation;
- reconciliation;
- retention deletion;
- notification delivery;
- knowledge indexing.

The scheduler may discover due work, but it invokes application use cases and persists jobs rather than bypassing domain and tenant-authorization boundaries.

## 6. Webhook flow

1. Receive request.
2. Validate route and provider connection.
3. Verify signature.
4. Enforce body-size and rate limits.
5. Compute idempotency key.
6. In one PostgreSQL transaction, persist the webhook event metadata, encrypted payload when permitted, and a pending outbox job.
7. Commit the transaction.
8. Return the provider-required success response quickly.
9. An outbox publisher claims committed pending jobs using concurrency-safe database semantics and publishes persisted job IDs to the queue.
10. A worker loads the persisted event by ID and normalizes it to canonical contracts.
11. Store the immutable message or message event and update derived projections transactionally.
12. Persist dependent outbox jobs in the same transaction as the state changes that require them.
13. Record bounded retry, failure, and dead-letter state without storing message bodies in logs.

The handler must be safe under duplicate and out-of-order delivery.

The queue is a delivery mechanism, not the source of truth. Queue messages contain persisted identifiers, not raw customer content. After a publisher crash, queue outage, or publish timeout, the publisher reclaims pending or timed-out outbox rows. Consumers are idempotent because publication may occur more than once. A reconciliation job detects outbox rows that remain unpublished or unprocessed beyond policy and raises metadata-only alerts.

## 7. Canonical data model

Provider adapters map external events to internal versioned contracts.

Canonical message fields include:
- schema version;
- tenant ID;
- channel connection ID;
- conversation thread ID;
- optional sales case ID;
- external conversation ID;
- external message ID;
- sender type;
- direction;
- sent time;
- received time;
- reply reference;
- content type;
- encrypted raw-content reference;
- sanitized content;
- provider metadata;
- processing state.

An original Message is immutable. Provider-reported edits, deletes, and delivery-state changes are separate immutable events. Current content, deletion state, and delivery state are derived projections that can be rebuilt from source records. Arrival order must not overwrite a newer provider state.

A `ConversationThread` belongs to exactly one provider connection and external conversation. An optional `SalesCase` groups related threads, resolved identities, and CRM deals without merging their source histories. Identity-resolution and grouping provenance are retained and reviewable.

### 7.1 Encrypted content storage (Block HI)

Raw message bodies, sanitized bodies, and optional provider webhook payloads are
stored in `encrypted_contents` as AES-256-GCM ciphertext with per-content DEKs.
Canonical tables keep `content_id` references only. See `docs/ENCRYPTED_CONTENT.md`
and ADR-0012.

### 7.2 Transactional outbox tables (Block HI)

Accepted state changes that require asynchronous work enqueue rows in `outbox_jobs`
in the same PostgreSQL transaction. Publishers emit job UUIDs only; consumers
reload authorized state from PostgreSQL. See `docs/OUTBOX.md`.

### 7.3 Privacy redaction and deterministic metrics (Block LM)

After canonical message storage, ingestion enqueues `content.redact`. The worker
decrypts raw UTF-8 message bodies locally, runs deterministic detection
(`lm-detector-v1`), replaces structured findings with stable placeholders, and
re-scans to fail closed on residual matches. Eligible output is encrypted as
`sanitized_message` and linked from `content_sanitizations`; blocked content never
writes sanitized ciphertext.

External AI (`message.analyze`) consumes sanitized ciphertext only when eligibility
and ADR-0005 gates allow. Block LM does not call external LLM providers.

Operational metrics are computed separately from message bodies. `MetricsEngine`
reads canonical metadata inside half-open tenant-local windows, persists immutable
`metric_snapshots` keyed by `formula_version`, and is triggered by
`metrics.recalculate` jobs (including after eligible redaction). See
`docs/PRIVACY_REDACTION.md`, `docs/METRICS.md`, and ADR-0014.

### 7.4 Governed AI gateway and knowledge retrieval (Block NOPQ)

NOPQ adds provider-neutral AI and tenant-isolated knowledge foundations:

- `AiGateway` orchestrates sanitized transcript assembly, policy/input gating,
  budget reservation, knowledge retrieval, provider call, and strict output validation.
- Output is accepted only when schema, issue taxonomy, evidence IDs, and knowledge
  citations are valid and no sensitive-data leakage is detected.
- Knowledge indexing runs through `knowledge.index` outbox jobs:
  approved encrypted documents are chunked, encrypted as `knowledge_chunk`, and
  indexed with tenant-keyed lexical term digests.
- Retrieval is tenant-scoped, ranked deterministically, and decrypts chunks with
  `ContentAccessPurpose.KNOWLEDGE_RETRIEVAL`, including audit append.

NOPQ does not yet expose public analysis/knowledge API routes and does not wire
`message.analyze` as an active worker handler.

### 7.5 WhatsApp Cloud provider boundary (Block VW)

Official Meta WhatsApp Cloud integration stays inside infrastructure adapters:

- `WhatsAppCloudWebhookAdapter` verifies `X-Hub-Signature-256` and normalizes
  webhook JSON to canonical operations;
- `WhatsAppCloudApiClient` calls versioned Graph endpoints via `httpx` with
  injectable transport (MockTransport in tests);
- `WhatsAppCredentialResolver` resolves access token, app secret, and verify token
  by reference key — secrets never persist in PostgreSQL or API responses;
- inbound media stores placeholder text and `quarantined_pending_scan` metadata until
  a scanner adapter exists;
- outbound uses human-approved drafts, `WhatsAppMessagingPolicy` v1, and
  `provider.message.send` handler with no blind resend.

Provider SDK types and raw webhook JSON must not leak into domain packages.
See `docs/WHATSAPP_CLOUD.md` and ADR-0016.

## 8. Consistency

- PostgreSQL is the primary system of record.
- Redis is not a source of truth.
- Queue jobs reference persisted IDs rather than carrying raw customer content.
- Write operations use explicit transactions.
- Derived analytics can be recomputed from source records.
- Use the transactional outbox pattern whenever an accepted external event or internal state change must reliably enqueue work.
- Outbox recovery and reconciliation are required operational capabilities, not optional optimizations.

## 9. Multi-tenancy

Defense in depth:
- application-layer authorization;
- tenant-scoped repository methods;
- composite indexes;
- optional PostgreSQL row-level security;
- tenant-aware cache keys;
- tenant-aware object paths;
- separate encryption context per tenant where practical.

Cross-tenant access tests are release-blocking.

## 10. Deployment topology

Initial production topology:

```text
reverse proxy
web container
api container
worker container
scheduler container
PostgreSQL
Redis
S3-compatible object storage
monitoring and log pipeline
backup target
```

All components handling personal data must be deployed only after jurisdiction and provider approval.

## 11. Observability

Collect:
- request count and latency;
- webhook verification failures;
- duplicate-event rate;
- job latency and failure;
- dead-letter count;
- provider connection health;
- LLM latency, cost, and validation failure;
- redaction block rate;
- data freshness;
- database and queue health.

Never put message bodies or secrets in logs, traces, or error-reporting breadcrumbs.

## 12. Failure strategy

- Provider outage: persist and reconcile later.
- LLM outage: mark analysis pending; do not lose messages.
- Invalid AI output: reject, retry within budget, then human review.
- Revoked token: stop calls and surface connection action.
- Queue outage: synchronous ingestion persists the accepted webhook event and pending outbox job atomically; publication resumes after recovery.
- Outbox publisher crash or ambiguous publish result: reclaim timed-out jobs and republish; consumers remain idempotent.
- Duplicate webhook: idempotently return success.
- Partial CRM sync: surface stale status and run reconciliation.
- Missing CRM connection: display CRM-dependent metrics as unavailable.
- Stale CRM sync: display CRM-dependent metrics as stale with the last successful sync time.
- AI must never infer factual qualified, won, or lost outcomes.
- Redaction uncertainty: block external AI call.

## 13. Scaling path

Extract a module into a service only when:
- it has a measured independent scaling problem;
- deployment isolation materially reduces risk;
- transactional coupling is understood;
- observability exists;
- an ADR is accepted.

Possible future extraction candidates:
- high-volume ingestion;
- AI processing;
- reporting;
- notification delivery.

This is a future option, not an initial goal.
