# Backup and Restore

PostgreSQL is the CloserOS system of record. Backups must be encrypted at rest
and stored in the approved jurisdiction.

## Supabase automated backups

Enable Supabase point-in-time recovery on staging/production projects where the
plan supports it. Record retention in the tenant data processing register.

## Logical backups (operator)

Use `scripts/ops/backup_pg.sh` to **generate** (and optionally run) `pg_dump`:

```bash
export DATABASE_URL='postgresql://...'
./scripts/ops/backup_pg.sh --output closeros-staging-$(date -u +%Y%m%d).dump
# Review printed command, then:
./scripts/ops/backup_pg.sh --output closeros-staging.dump --execute
```

Default mode is dry-run — it prints the command without executing.

Safety checks:

- Refuses known local/CI credential markers unless `--allow-unsafe`.
- Never prints the full `DATABASE_URL`.

## Restore

Use `scripts/ops/restore_pg.sh`:

```bash
./scripts/ops/restore_pg.sh \
  --input closeros-staging.dump \
  --database-url "$DATABASE_URL" \
  --confirm-destructive \
  --dry-run

# After review:
./scripts/ops/restore_pg.sh \
  --input closeros-staging.dump \
  --database-url "$DATABASE_URL" \
  --confirm-destructive \
  --execute
```

Non-local restores require `--confirm-destructive`.

## When to backup

- Before every production-impacting migration
- Before CRM or messaging provider credential rotation affecting stored tokens
- Before major data backfill jobs
- On compliance request

## Redis

Redis is **not** backed up for message truth. Rebuild streams from PostgreSQL
outbox reconciliation after Redis loss (`docs/OUTBOX.md`).

## Restore testing

Block Z requires quarterly restore drills to a disposable database verifying:

1. Alembic head matches expectation.
2. Authentication and tenant isolation smoke tests pass.
3. No customer data from production is used in non-production drills without
   anonymization approval.

## Related documentation

- `docs/RETENTION_LEGAL_HOLD.md`
- `docs/MIGRATION_RUNBOOK.md`
- `docs/STAGING_SUPABASE.md`
