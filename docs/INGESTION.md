# Ingestion pipeline

## Overview

CloserOS ingests provider events through a provider-neutral adapter boundary. HTTP
webhook acceptance is fast and transactional; normalization runs asynchronously via
the PostgreSQL outbox and Redis Streams delivery layer.

## Webhook flow

1. `POST /api/v1/webhooks/{provider}/{connection_id}` receives raw bytes (max 1 MiB).
2. Connection status and provider kind are validated without revealing existence.
3. Rate limiting runs before expensive work.
4. The registered adapter verifies the signature on exact bytes.
5. One transaction encrypts the payload, creates `WebhookEvent`, enqueues
   `webhook.normalize`, and appends audit.
6. HTTP returns a generic accepted response.
7. Publisher claims the outbox job and publishes the job UUID to Redis Streams.
8. Processor claims the published job and runs `WebhookNormalizeHandler`.
9. Handler decrypts with `webhook_normalization` purpose, normalizes operations,
   persists canonical entities idempotently, enqueues `content.redact`, and marks the
   webhook processed.

## Adapter registry

- Keyed by controlled `ProviderKind` values.
- Duplicate registration is rejected.
- Production requires explicit adapter injection.
- **Synthetic adapter** (development/test only): HMAC-SHA-256 over raw body.

## Failure handling

| Failure | Behavior |
|---------|----------|
| Invalid signature | Generic HTTP denial |
| Unknown/inactive connection | Generic HTTP denial |
| Duplicate external event | Generic accepted; no duplicate rows |
| Malformed provider payload | Permanent failure → dead letter |
| Transient persistence error | Outbox retry with exponential backoff |

## Operational reconciliation

Run `closeros-worker reconcile-once` (or `all`) to recover expired publisher/processor
claims and report overdue pending and dead-letter counts. Metadata-only logs only.

## Worker modes

```bash
closeros-worker publisher
closeros-worker processor
closeros-worker reconcile-once
closeros-worker all
```

## Security

Never log request bodies, signatures, external event IDs, connection IDs, or credentials.
Queue messages carry job UUIDs only.
