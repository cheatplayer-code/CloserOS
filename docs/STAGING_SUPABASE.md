# Staging — Supabase PostgreSQL

Supabase provides managed PostgreSQL for CloserOS staging. See also
`infra/supabase/README.md`.

## Provisioning

1. Create a Supabase project in the approved jurisdiction.
2. Enable SSL connections only.
3. Copy the **connection pooler** URI (port `6543`) for application services.
4. Store the URI as `DATABASE_URL` in Railway (API + worker). Never commit it.

Direct session connections (port `5432`) are for migrations and DBA tasks only.

## Migrations

Alembic revisions in `packages/backend/src/closeros/infrastructure/migrations`
are authoritative.

```bash
# Read-only status
uv run python scripts/ops/migrate_status.py --database-url "$DATABASE_URL"

# Upgrade (staging requires --confirm)
uv run python scripts/ops/migrate_upgrade.py --database-url "$DATABASE_URL" --confirm
```

Run migrations from a controlled operator environment or a Railway one-off job
before rolling out API/worker images that depend on new schema.

## What we do not use

- Supabase Auth — CloserOS uses self-hosted opaque sessions (ADR-0010).
- Supabase Realtime — outbox uses PostgreSQL + Redis Streams.
- Supabase SQL as schema source of truth — emergency SQL must be backported.

## Backups

Supabase provides automated backups on paid tiers. CloserOS operators also run
logical backups before risky migrations (`docs/BACKUP_RESTORE.md`).

## Security

- Restrict network access to Railway egress where the plan allows.
- Rotate credentials through Supabase; update Railway variables atomically.
- Staging must not contain real customer exports or production message bodies.
- Never log `DATABASE_URL` or query results with message content.

## Failure modes

| Symptom | Action |
|---------|--------|
| API `/ready` 503 | Check pooler URI, SSL mode, IP allow list |
| Migration pending | Run `migrate_status.py`; upgrade before deploy |
| Connection saturation | Lower API pool size; verify pooler vs direct URI |
