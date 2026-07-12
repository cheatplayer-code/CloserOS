# Transactional outbox

Block HI implements the PostgreSQL-backed transactional outbox foundation
required by ADR-0006 and ADR-0012. The queue carries job UUIDs only;
PostgreSQL is the source of truth.

## Scope

Implemented in Block HI:

- framework-independent `OutboxJob` domain with explicit state machine;
- `outbox_jobs` and `outbox_job_attempts` tables (revision `e7a1c3d5f9b2`);
- concurrency-safe claim, publish, process, retry, dead-letter, and expired-claim
  recovery;
- `OutboxPublisherService`, `OutboxProcessorService`, and
  `OutboxReconciliationService`;
- `QueuePublisher` port (job UUID publication only);
- atomic enqueue with encrypted-content and canonical writes;
- deduplication keys per tenant (and global deduplication for
  `reconciliation.run`).

Not implemented in Block HI:

- concrete Redis or other queue adapter wired in production;
- scheduler/worker process entry points;
- real handlers for `webhook.normalize`, `content.redact`, `message.analyze`, etc.;
- dead-letter operator UI;
- outbox row retention cleanup job.

## State machine

```text
                    +-----------+
                    |  pending  |
                    +-----+-----+
                          | claim (publisher)
                          v
                    +-----------+
            +------>| publishing|------+
            |       +-----------+      |
            | lease expired          publish OK
            | (reconcile)                |
            v                            v
      +-----------+              +-----------+
      |  pending  |              | published |
      +-----------+              +-----+-----+
                                        | claim (processor)
                                        v
                                  +-----------+
                          +-------->| processing|--------+
                          |         +-----------+        |
                          | lease expired              success
                          | (reconcile)                    |
                          v                                v
                    +-----------+                    +-----------+
                    | published |                    | succeeded |
                    +-----------+                    +-----------+

retry_scheduled <--- publish/process failure (attempts remain)
dead_letter     <--- publish/process failure (attempts exhausted)
cancelled       <--- explicit cancellation (future)
```

### States

| State | Meaning |
|-------|---------|
| `pending` | Committed, waiting for publisher claim |
| `publishing` | Publisher holds lease; queue publish in flight |
| `published` | Job UUID enqueued; waiting for processor claim |
| `processing` | Processor holds lease; handler executing |
| `retry_scheduled` | Backoff elapsed before next publisher claim |
| `succeeded` | Handler completed successfully |
| `dead_letter` | Attempt budget exhausted; requires operator review |
| `cancelled` | Intentionally abandoned (reserved) |

### Leases and retries

| Phase | Lease | Default max attempts |
|-------|-------|---------------------|
| Publisher | 60 seconds | 10 |
| Processor | 300 seconds | 10 |

Retry delay: `min(3600, 30 × 2^(attempt-1))` seconds (no jitter).

Claims require matching `claim_token` and `expected_version`. Each successful
transition increments `version`.

## Write path

Outbox rows are inserted in the **same transaction** as the business mutation.

Block HI atomic commands demonstrate:

- `store_raw_message` — encrypted content + `messages` + `content.redact` job +
  audit;
- `store_message_edit` — encrypted content + `message_edit_events` +
  `content.redact` job + audit;
- `attach_provider_payload` — encrypted provider payload +
  `webhook_events.encrypted_payload_content_id` + `webhook.normalize` job + audit.

Deduplication keys prevent duplicate jobs for the same resource within a tenant,
for example `content_redact_{message_id}` and
`webhook_normalize_{webhook_event_id}`.

## Publication

`OutboxPublisherService.publish_batch`:

1. Claims up to `batch_size` eligible jobs (`pending` or `retry_scheduled`,
   `available_at <= now`).
2. Calls `QueuePublisher.publish_job_id(job_id=...)`.
3. Marks `published` on success.
4. On publish failure, schedules retry or dead-letters when attempts are exhausted.
5. Records each attempt in `outbox_job_attempts` with phase `publisher`.

Queue messages contain **only the job UUID**. Consumers must not expect business
payloads in Redis.

## Processing

`OutboxProcessorService` claims `published` jobs and dispatches to a handler map
keyed by `OutboxJobKind`. Block HI includes `NoOpOutboxJobHandler` for tests.

On handler failure:

- retry with backoff when attempts remain;
- `dead_letter` with `last_error_code` when budget is exhausted.

Successful processing marks `succeeded` and records a `processor`-phase attempt.

## Crash and recovery

| Failure | Recovery |
|---------|----------|
| API crash after commit, before publish | Row stays `pending`; publisher picks it up |
| Publisher crash during `publishing` | Lease expires; reconciliation recovers to `pending` |
| Ambiguous publish (timeout) | Retry may duplicate queue message; consumer idempotent |
| Queue outage | Rows accumulate in PostgreSQL; publish resumes when queue returns |
| Processor crash during `processing` | Lease expires; reconciliation recovers to `published` |
| Handler timeout | Retry or dead-letter per attempt budget |

PostgreSQL retains all state. No accepted work is lost solely because Redis was
unavailable.

## Reconciliation

`OutboxReconciliationService.reconcile`:

1. Recovers expired publisher claims (`publishing` → `pending`).
2. Recovers expired processor claims (`processing` → `published`).
3. Reports bounded counts of overdue `pending` jobs and `dead_letter` jobs.

Reconciliation is metadata-only. It does not log message bodies or queue payloads.
Future schedulers will enqueue `reconciliation.run` jobs and raise alerts when
overdue counts exceed policy.

Audit action `outbox.reconciliation.completed` records reconciliation outcomes.

## Job kinds (initial)

| Kind | Tenant scope | Typical trigger |
|------|-------------|-----------------|
| `webhook.normalize` | tenant | Provider payload attached |
| `content.redact` | tenant | Raw message or edit stored |
| `message.analyze` | tenant | Future: post-redaction |
| `notification.deliver` | tenant | Future: human-approved outbound |
| `retention.delete` | tenant | Future: expiry worker |
| `knowledge.index` | tenant | Future: KB ingestion |
| `reconciliation.run` | global | Future: scheduler |

Handlers for most kinds are deferred to later blocks. Block JK adds ingestion
orchestration that enqueues and consumes `webhook.normalize` jobs.

## Future queue adapters

The `QueuePublisher` port isolates infrastructure from domain logic. Expected
adapters:

- **Redis list/stream publisher** (initial production candidate) — publishes job
  UUID strings only;
- **In-memory publisher** — unit and integration tests;
- **No-op publisher** — dry-run and disaster drills.

Adapter selection, connection pooling, and visibility timeout alignment with
processor leases require a future ADR when Block JK wires production workers.

Consumers must:

1. Load `outbox_jobs` by UUID with tenant authorization.
2. Ignore unknown or terminal states idempotently.
3. Reload business entities by `OutboxJobReference` fields.
4. Never depend on queue payload beyond the job UUID.

## Related documents

- `docs/adr/ADR-0006-transactional-outbox.md`
- `docs/adr/ADR-0012-envelope-encryption-and-transactional-outbox.md`
- `docs/ENCRYPTED_CONTENT.md`
- `docs/ARCHITECTURE.md` (sections 6, 8, 12)
- `packages/backend/src/closeros/infrastructure/migrations/README.md`
