# Staging — Supabase PostgreSQL

Supabase provides managed PostgreSQL for CloserOS staging. See also
`infra/supabase/README.md` and `docs/STAGING_SIGNOFF.md`.

## Provisioning

1. Create a dedicated staging Supabase project in the approved temporary staging
   region.
2. Enable SSL connections only.
3. For the persistent Railway API and worker, choose:
   - the **direct** connection on port `5432` when Railway can reach the project
     IPv6 endpoint; or
   - the Shared Pooler **session mode** connection on port `5432` when an
     IPv4-compatible connection is required.
4. Append `sslmode=require` or a stronger verification mode.
5. Store the URI as sealed/shared `DATABASE_URL` in Railway API and worker.
   Never commit it or expose it to Vercel.

Do **not** use Shared Pooler transaction mode on port `6543` with the current
persistent SQLAlchemy/psycopg runtime. Supabase documents transaction mode for
transient serverless/edge connections and notes that it does not support prepared
statements. CloserOS does not currently disable psycopg prepared statements for a
transaction pooler.

Direct or session connections on port `5432` are also used for controlled
migration and DBA tasks.

## Preflight

From a trusted operator environment containing the staging variables:

```bash
uv run python scripts/ops/staging_preflight.py --json
```

The preflight rejects local credentials, non-TLS database URLs, the transaction
pooler port, and non-Supabase hosts. It prints no connection credentials.

## Migrations

Alembic revisions in `packages/backend/src/closeros/infrastructure/migrations`
are authoritative.

```bash
# Read-only status
uv run python scripts/ops/migrate_status.py --json

# Upgrade (staging requires --confirm)
uv run python scripts/ops/migrate_upgrade.py --confirm
uv run python scripts/ops/migrate_status.py --json
```

Run migrations from a controlled operator environment or a Railway one-off job
before rolling out API/worker images that depend on new schema. Do not run schema
migration concurrently from every API replica.

## What we do not use

- Supabase Auth — CloserOS uses self-hosted opaque sessions (ADR-0010).
- Supabase Realtime — outbox uses PostgreSQL + Redis Streams.
- Supabase SQL as schema source of truth — emergency SQL must be backported as an
  Alembic revision.
- Supabase transaction pooler for the persistent API/worker runtime.

## Backups

Supabase provides automated backups according to the selected plan. CloserOS
operators also run and verify logical backups before risky migrations
(`docs/BACKUP_RESTORE.md`). Backup availability is not considered proven until
an S2/Z restore drill is recorded.

## Security

- Restrict network access to approved Railway egress where the plan allows.
- Rotate credentials through Supabase; update Railway variables atomically.
- Seal `DATABASE_URL` in Railway after verification.
- Staging must not contain real customer exports or production message bodies.
- Never log `DATABASE_URL`, database passwords, or query results containing
  message content.

## Failure modes

| Symptom | Action |
|---------|--------|
| API `/ready` 503 | Check direct/session URI, TLS mode, DNS/IPv6 reachability, and network restrictions |
| Prepared-statement/pooler errors | Confirm port is `5432`, not transaction mode `6543` |
| Migration pending | Stop rollout; run status then controlled upgrade |
| Connection saturation | Reduce application pool size and verify direct/session mode |
| Staging preflight rejects URL | Do not bypass the gate; correct the connection mode or TLS settings |
