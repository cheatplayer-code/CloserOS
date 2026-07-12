# ADR-0012: Envelope encryption and transactional outbox foundation

Status: accepted
Date: 2026-07-12
Decision owners: platform engineering

## Context

Block HI must store raw message bodies, sanitized message bodies, and optional
provider webhook payloads without persisting plaintext in PostgreSQL, queue
payloads, or logs. Canonical messages and webhook events already reference
`content_id`; Block FG deferred ciphertext storage and the transactional outbox.

ADR-0006 accepts the transactional outbox pattern but does not define claim
semantics, retry policy, or encrypted-content cryptography. `SECURITY_COMPLIANCE.md`
requires application-level encryption for raw message content and documented key
management.

## Decision

### Envelope encryption

Use **AES-256-GCM envelope encryption** through the maintained `cryptography`
library. Do not implement custom cryptography.

For every encrypted content record:

1. Generate a fresh **per-content data encryption key (DEK)** — 32 random bytes.
2. Encrypt the plaintext with AES-256-GCM using a 12-byte content nonce and
   **content AAD** bound to tenant, content ID, kind, encoding, and AAD version.
3. Wrap the DEK with the active **key encryption key (KEK)** using AES-256-GCM,
   a 12-byte key-wrap nonce, and **key-wrap AAD** bound to tenant, content ID,
   key version, and AAD version.
4. Persist only ciphertext, nonces, wrapped DEK, algorithm identifier, key
   version, AAD version, and `plaintext_byte_length` — never plaintext.

Content AAD format (version 1):

```text
closeros-content-v{aad_version}|{tenant_id}|{content_id}|{kind}|{encoding}
```

Key-wrap AAD format (version 1):

```text
closeros-dek-wrap-v{aad_version}|{tenant_id}|{content_id}|{key_version}
```

AAD binding prevents ciphertext swap, cross-tenant reuse, and kind/encoding
confusion. AAD version increments only through an explicit ADR when the binding
format changes.

Supported kinds:

- `raw_message` — up to 256 KiB plaintext;
- `sanitized_message` — up to 256 KiB plaintext;
- `provider_payload` — up to 1 MiB plaintext.

Encodings: `utf8`, `json`, `binary`.

### Key provider / KMS boundary

Domain and application layers depend on ports only:

- `KeyProvider` — active key version, version listing, DEK wrap/unwrap;
- `DataKeyCryptography` — encrypt, decrypt, and rewrap operations;
- `SecureRandom` — cryptographically secure byte generation.

Infrastructure supplies `AesGcmContentCryptography` and a production key-provider
adapter. `StaticKeyProvider` is permitted for local development and automated
tests only. Production composition must inject an explicit production-grade
adapter or fail closed through `require_production_key_provider`.

KEK material never appears in PostgreSQL, queue messages, logs, or exception
messages. KMS/HSM integration is a future infrastructure adapter behind
`KeyProvider`, not a domain concern.

### Key versions and rotation

Each encrypted row stores the `key_version` used to wrap its DEK. Unwrap always
uses the stored version. New writes and rewraps use `active_key_version`.

Rotation is **rewrap-only**:

1. Unwrap the DEK with the stored key version.
2. Re-wrap with the active KEK and a fresh key-wrap nonce.
3. Update wrapped DEK fields and `key_version`; ciphertext and content nonce
   remain unchanged.

Old key versions remain available until every row referencing them is rewrapped.
Rewrap is audited as `encrypted_content.key_rewrapped`. Bulk rewrap workers are
future operational work.

### PostgreSQL ciphertext storage

Table: `encrypted_contents` (revision `e7a1c3d5f9b2`).

- composite primary uniqueness: `(tenant_id, id)`;
- tenant-scoped composite foreign keys from `messages.content_id`,
  `message_edit_events.content_id`, and `webhook_events.encrypted_payload_content_id`;
- retention `expires_at` derived from tenant retention policy;
- indexes on `(tenant_id, kind, created_at)`, `(tenant_id, expires_at)`,
  `(tenant_id, key_version)`, and `(expires_at, tenant_id)`.

Canonical tables store `content_id` references only. No plaintext column exists
on message, webhook, or outbox tables.

### Transactional outbox foundation

Table: `outbox_jobs` with append-only `outbox_job_attempts` (revision
`e7a1c3d5f9b2`).

Persist outbox jobs in the **same PostgreSQL transaction** as the state change
that requires asynchronous work. Atomic commands in Block HI demonstrate this
for encrypted content + canonical writes + outbox enqueue + audit append.

Outbox rows carry:

- tenant-scoped or global job kind;
- resource reference (`resource_type`, `resource_id`, optional `secondary_id`,
  `schema_version`);
- deduplication key;
- priority, attempt budget, optimistic `version`, and claim metadata.

Initial job kinds: `webhook.normalize`, `content.redact`, `message.analyze`,
`notification.deliver`, `retention.delete`, `knowledge.index`,
`reconciliation.run`.

### Queue IDs only

The queue is a delivery mechanism, not the source of truth. The outbox publisher
publishes **only the outbox job UUID** through the `QueuePublisher` port.
Consumers reload authorized business state from PostgreSQL by persisted
identifiers. Queue payloads must not contain raw customer content, DEKs, KEKs,
or provider tokens.

### At-least-once publication

Publication is **at-least-once**. Duplicate queue delivery is expected.
Consumers must be idempotent and authoritative reads must come from PostgreSQL.

Publisher flow:

1. Claim eligible `pending` or `retry_scheduled` rows (`publishing`, 60s lease).
2. Publish job UUID to the queue.
3. Mark `published` on success.
4. On failure, schedule exponential backoff retry or move to `dead_letter` when
   `max_attempts` is exhausted.

Processor flow:

1. Claim `published` rows (`processing`, 300s lease).
2. Dispatch to a handler registered by `job_kind`.
3. Mark `succeeded`, schedule retry, or dead-letter on outcome.

Default retry: 30s base, ×2 multiplier, 3600s cap, 10 max attempts.

### Lease, retry, and dead-letter

Claims use a random `claim_token`, `claimed_by` worker ID, and
`claim_expires_at`. State transitions require matching `claim_token` and
`expected_version`. Expired publisher claims recover to `pending`; expired
processor claims recover to `published`.

`OutboxReconciliationService` recovers expired claims and reports bounded
metadata-only counts for overdue pending and dead-letter jobs. Reconciliation
does not publish or process jobs directly.

### PostgreSQL source of truth

PostgreSQL remains authoritative for encrypted content, outbox state, canonical
records, and audit events. Redis is not a source of truth. After any crash,
queue outage, or ambiguous publish result, work remains recoverable from
PostgreSQL through reclaim, retry, and reconciliation.

## Alternatives considered

1. **Column-level database encryption only** — rejected; does not provide
   per-content DEK isolation, explicit AAD binding, or a clean KMS boundary.
2. **Single global DEK per tenant** — rejected; widens blast radius on key
   compromise and complicates rotation.
3. **Queue payloads with encrypted blobs** — rejected; duplicates ciphertext,
   complicates idempotency, and increases leakage surface in Redis diagnostics.
4. **Exactly-once queue delivery** — rejected as unnecessary; idempotent
   consumers with PostgreSQL authority are sufficient.
5. **Redis-backed outbox** — rejected by ADR-0006 and architecture policy.

## Consequences

- Every content decrypt and rewrap requires an audited access purpose.
- Production deployment requires a real `KeyProvider` adapter and KEK custody
  decision before storing customer content.
- Workers and publishers must run with distinct `worker_id` values and bounded
  batch sizes.
- Block JK will add ingestion orchestration and concrete queue adapters on top
  of this foundation.
- Handler implementations for most job kinds remain future work; Block HI ships
  domain, persistence, publisher/processor services, and a no-op handler for
  tests.

## Security and privacy impact

- Plaintext exists only in process memory during encrypt/decrypt operations.
- Ciphertext, wrapped DEKs, and nonces must not appear in logs, traces, or error
  breadcrumbs.
- Decrypt access is purpose-gated (`redaction`, `webhook_normalization`,
  `ai_analysis`, `audit_review`, `retention_deletion`, `key_rewrap`).
- Cross-tenant content access is blocked by composite foreign keys and
  tenant-scoped repository lookups.
- `StaticKeyProvider` must never be used in production.

## Migration and rollback/remediation

Revision `e7a1c3d5f9b2` chains from `d4e8f1a2b3c5`. Downgrade drops outbox
tables, removes content foreign keys, and drops `encrypted_contents`. Safe only
on an empty schema or isolated test database. On populated production data, use
expand/migrate/contract.

If publication is disabled, pending rows remain in PostgreSQL and resume after
recovery. Dead-letter rows require operator review; do not delete before retention
and investigation policies are satisfied.

## Sources verified

- NIST SP 800-38D (AES-GCM) — reviewed 2026-07-12
- `cryptography` AESGCM documentation — reviewed 2026-07-12
- CloserOS `AGENTS.md`, `docs/SECURITY_COMPLIANCE.md`, ADR-0006 — reviewed
  2026-07-12
- CloserOS Block HI implementation under `packages/backend` — reviewed
  2026-07-12
