# Worker Operations

The CloserOS worker (`closeros-worker`) processes the transactional outbox:
publishing job UUIDs to Redis Streams and executing handlers in PostgreSQL.

## CLI

```bash
uv run closeros-worker <mode>
```

| Mode | Purpose | Typical deployment |
|------|---------|-------------------|
| `publisher` | Claims outbox rows and publishes UUIDs to Redis | Long-running |
| `processor` | Reads Redis stream and executes handlers | Long-running |
| `all` | Runs publisher and processor concurrently | **Railway default** |
| `reconcile-once` | Requeues overdue outbox jobs | Cron / manual |
| `reconcile-whatsapp-once` | WhatsApp-specific reconciliation | Cron; needs `WHATSAPP_RECONCILE_TENANT_ID` |

Docker image CMD: `closeros-worker all` (`infra/docker/Dockerfile.worker`).

## Required environment

| Variable | Description |
|----------|-------------|
| `APP_ENV` | `production` in staging/prod |
| `DATABASE_URL` | PostgreSQL (Supabase pooler) |
| `REDIS_URL` | Redis with password/TLS |
| `APP_ENCRYPTION_KEY` | Content encryption |
| `OUTBOX_STREAM` | Default `closeros.outbox.jobs` |
| `OUTBOX_CONSUMER_GROUP` | Default `closeros.outbox.processors` |
| `WORKER_ID` | Unique per replica (auto-generated if unset) |

Tuning:

- `WORKER_POLLING_INTERVAL_SECONDS` (publisher sleep)
- `WORKER_PUBLISH_BATCH_SIZE`
- `WORKER_PROCESSOR_BLOCK_MS` (Redis `XREADGROUP` block)

## Handler kinds (current)

Includes JK ingestion, LM redaction/metrics, NOPQ analysis/knowledge, VW provider
send/template sync. CRM handlers arrive with Bitrix24 adapter work.

## Scaling guidance

1. Start with **one** worker replica until lag metrics exist.
2. Scale processors horizontally; use distinct `WORKER_ID` per replica.
3. Do not scale publishers beyond one without lease contention analysis.
4. Monitor dead-letter and `outbox_job_attempts` tables.

## Failure modes

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Jobs stuck in `pending` | Publisher down | Restart publisher / `all` |
| Redis connection errors | `REDIS_URL` wrong | Fix secret, restart |
| Handler exceptions | Schema drift | Check migration status |
| Growing stream lag | Processor capacity | Scale worker, inspect slow handlers |

## Graceful shutdown

`SIGINT`/`SIGTERM` stop the publisher/processor loops and dispose DB pools.
Railway sends SIGTERM on deploy; allow sufficient drain timeout.

## Reconciliation cron (recommended)

Run every 5 minutes:

```bash
closeros-worker reconcile-once
```

as a Railway cron service or external scheduler with the same secrets as the worker.

## Related documentation

- `docs/OUTBOX.md`
- `docs/STAGING_RAILWAY.md`
- `docs/OBSERVABILITY.md`
- `scripts/ops/` migration helpers (schema must be current before worker deploy)
