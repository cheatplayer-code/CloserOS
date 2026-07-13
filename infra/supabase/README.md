# Supabase (PostgreSQL) — staging reference

CloserOS uses **Supabase-hosted PostgreSQL** for staging database capacity.
Supabase Auth, Storage, and Edge Functions are **not** part of the CloserOS
architecture in Block XY.

## Role in the stack

| Concern | Owner |
|---------|-------|
| PostgreSQL schema and migrations | CloserOS repository (`packages/backend/.../migrations`) |
| Connection string (`DATABASE_URL`) | Supabase project settings → injected into Railway API/worker |
| Row data and backups | Supabase project + CloserOS runbooks |
| Application authentication | CloserOS self-hosted sessions (ADR-0010) |
| Object storage for media | Approved jurisdiction S3-compatible store (future Z hardening) |

## Connection strings

Use the **connection pooler** URI for API and worker services:

```text
DATABASE_URL=postgresql://<user>:<password>@<pooler-host>:6543/postgres?sslmode=require
```

Direct (session) connections are reserved for one-off migrations and DBA tasks.
Never embed credentials in the repository.

## Migrations are authoritative

Schema changes ship only through Alembic revisions in this repository:

```bash
# Status (dry, metadata only)
uv run python scripts/ops/migrate_status.py --database-url "$DATABASE_URL"

# Upgrade to head (requires explicit confirmation flag in staging/production)
uv run python scripts/ops/migrate_upgrade.py --database-url "$DATABASE_URL" --confirm
```

Supabase SQL editor changes must not become the source of truth. If emergency SQL
is applied manually, backport an Alembic revision before the next deploy.

## What we do not use

- Supabase Auth (CloserOS issues opaque server-side sessions)
- Supabase Realtime for outbox delivery (Redis Streams + PostgreSQL outbox)
- Supabase Storage for encrypted message bodies (encrypted PostgreSQL + future object store)

## Security checklist

- Enable SSL (`sslmode=require` minimum).
- Restrict database access to Railway egress IPs where Supabase plan allows.
- Rotate database passwords through Supabase dashboard; update Railway variables.
- Never log `DATABASE_URL` or query results containing message content.
- Staging databases must not hold real customer exports.

## Related documentation

- `docs/STAGING_SUPABASE.md`
- `docs/MIGRATION_RUNBOOK.md`
- `docs/BACKUP_RESTORE.md`
- `docs/SECRET_MANAGEMENT.md`
