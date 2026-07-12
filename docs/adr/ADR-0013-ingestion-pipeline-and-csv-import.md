# ADR-0013: Provider ingestion pipeline and controlled CSV import

Status: Accepted
Date: 2026-07-12

## Context

Block HI established encrypted content storage and a PostgreSQL transactional outbox.
Block JK must accept provider webhooks and controlled CSV imports without storing
plaintext in PostgreSQL, without logging message bodies, and without claiming any
official messaging provider integration.

## Decision

### Provider adapter boundary

- Framework-independent ports (`ProviderWebhookAdapter`, `ProviderAdapterRegistry`,
  `ProviderCredentialResolver`) isolate provider-specific verification and normalization.
- Production starts only with explicitly injected adapters; no dynamic import from
  client input.
- A **synthetic HMAC adapter** exists for development and tests only.

### Webhook verification and acknowledgement

- `POST /api/v1/webhooks/{provider}/{connection_id}` verifies signatures on exact raw
  bytes (max 1 MiB) before persistence.
- Atomic acceptance in one PostgreSQL transaction: encrypt `provider_payload`, create
  `WebhookEvent`, enqueue `webhook.normalize`, append audit, commit.
- Duplicate external events return the same generic accepted response without duplicate
  rows or jobs.
- Normalization runs asynchronously via the outbox processor, not in the HTTP request.

### Redis Streams as delivery only

- Stream field: `job_id` (UUID) only.
- PostgreSQL outbox remains the source of truth.
- At-least-once publication; duplicate Redis deliveries are expected and safe.
- Expired claims are recovered by reconciliation and republishing.

### Controlled CSV import

- Tenant-authenticated preview/start/status/cancel routes with CSRF, Origin, and
  OWNER/COMPLIANCE_ADMIN authorization.
- `X-Lawful-Source-Confirmed: true` required before upload.
- Source CSV encrypted as `csv_import` kind (max 10 MiB); no plaintext CSV in PostgreSQL.
- Integer-index mapping only; column labels returned for UI are not persisted in plaintext.
- Row errors store row number and safe error code only.
- `csv.import` jobs process 250-row resumable chunks with checkpoint commits.

### Supported worker job kinds (JK)

Workers publish/process only `webhook.normalize` and `csv.import`. Future kinds remain
pending until their implementation blocks; they are not dead-lettered merely for
missing handlers.

## Consequences

- Official WhatsApp, Instagram, and Telegram adapters are deferred to Block VW.
- PII redaction (`content.redact`) remains a separate Block LM handler.
- Production requires explicit KMS/key-provider, adapter, Redis, and scanner configuration.
