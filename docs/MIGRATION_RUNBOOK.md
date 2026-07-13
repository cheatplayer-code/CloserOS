# Migration Runbook

Alembic migrations in `packages/backend/src/closeros/infrastructure/migrations`
are the only approved schema change path.

## Before migrating

1. Read the revision docstring and migration file for locking risk.
2. Confirm API and worker versions are compatible with the target revision.
3. Take a logical backup (`docs/BACKUP_RESTORE.md`).
4. Check status:

```bash
uv run python scripts/ops/migrate_status.py --database-url "$DATABASE_URL"
```

## Staging upgrade

```bash
# Dry-run safety validation
uv run python scripts/ops/migrate_upgrade.py \
  --database-url "$DATABASE_URL" \
  --confirm \
  --dry-run

# Execute
uv run python scripts/ops/migrate_upgrade.py \
  --database-url "$DATABASE_URL" \
  --confirm
```

Non-local hosts require `--confirm` to prevent accidental production execution
from a developer laptop.

## Deploy coordination

| Migration type | Deploy order |
|----------------|--------------|
| Expand-only (new tables/columns) | Migrate → deploy API/worker |
| Contract (drop/rename) | Multi-phase expand/migrate/contract per ADR |
| Data backfill job | Migrate → deploy worker with backfill handler → verify |

Never drop populated columns in a single release.

## Rollback

Alembic downgrade is for **non-production** verification and CI tests only.
Production rollback uses forward-fix migrations or restore from backup — not
`alembic downgrade` on live data.

## Verification

```bash
uv run python scripts/ops/migrate_status.py --database-url "$DATABASE_URL"
# pending upgrade should be "no"
```

Run targeted pytest migration modules when changing schema:

```bash
uv run pytest tests/test_platform_migrations.py -q
```

## Emergency manual SQL

If manual SQL is applied in Supabase during an incident:

1. Stop further deploys.
2. Backport an Alembic revision matching the manual change.
3. Record incident in `PROJECT_STATUS.md` and open ADR if architectural.

## Related documentation

- `docs/STAGING_SUPABASE.md`
- `infra/supabase/README.md`
- `docs/BACKUP_RESTORE.md`
