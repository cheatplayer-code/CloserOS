# Synthetic Staging Smoke Runbook

This runbook boots a **synthetic-only** product demonstration without live
provider integrations, without manual PostgreSQL edits, and without Docker on the
operator laptop when managed PostgreSQL and Redis are available.

**Not production-ready.** This path validates application behavior with fabricated
data only.

## Safety defaults

Keep these disabled unless an approved sandbox is explicitly in scope:

| Variable | Value |
|----------|-------|
| `AI_EXTERNAL_CALLS_ENABLED` | `false` |
| `WHATSAPP_ENABLED` | `false` |
| `CRM_ENABLED` | `false` |
| `NOTIFICATIONS_ENABLED` | `false` (unless approved SMTP sandbox) |
| `MEDIA_SCANNER_ENABLED` | `false` |

Development encryption uses the deterministic `dev-kek-v1` key material wired in
API/worker development composition and operator scripts (`build_ops_content_encryption_service`).
Production uses remote KMS variables documented in `docs/ENVIRONMENT_VARIABLES.md`.

## Prerequisites

- Python **3.13.14**, Node **24.14.1**, pnpm **11.11.0**, uv **0.11.28**
- PostgreSQL reachable via `DATABASE_URL`
- Redis reachable via `REDIS_URL` (worker outbox)
- Alembic migrations at head
- Synthetic test user email on domain `example.invalid` only

## No-Docker option

Use managed services plus local executables:

| Component | Option |
|-----------|--------|
| PostgreSQL | Managed instance (e.g. Supabase) — set `DATABASE_URL` |
| Redis | Managed instance — set `REDIS_URL` |
| API | Local: `corepack pnpm run dev:api` |
| Worker | Local: `corepack pnpm run dev:worker` |
| Web | Local: `corepack pnpm run dev:web` |

Copy `.env.example` to an untracked `.env` and set `DATABASE_URL`, `REDIS_URL`,
`AUTH_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL`, and auth secrets.

## Procedure (exact order)

### 1. Register a synthetic test user

Open the web UI (`http://localhost:3000`), register with an address such as
`owner@example.invalid`, and use a strong password stored only in your local
password manager.

### 2. Verify email

Use development capture delivery (API tests) or an approved SMTP sandbox to
complete email verification. The bootstrap command rejects unverified users.

### 3. Run migrations

```bash
uv run python scripts/ops/migrate_upgrade.py
uv run python scripts/ops/migrate_status.py
```

### 4. Bootstrap the first tenant

```bash
uv run python scripts/ops/bootstrap_tenant.py \
  --owner-email owner@example.invalid \
  --tenant-name "Synthetic Demo Tenant" \
  --time-zone Asia/Almaty \
  --confirm
```

Save the returned `tenant_id`. Dry-run first with `--dry-run` if desired.

### 5. Seed synthetic demo data

```bash
uv run python scripts/ops/seed_synthetic_demo.py \
  --tenant-id <TENANT_UUID> \
  --confirm-synthetic-only
```

Optional reset of prior synthetic rows for the tenant:

```bash
uv run python scripts/ops/seed_synthetic_demo.py \
  --tenant-id <TENANT_UUID> \
  --confirm-synthetic-only \
  --reset-existing-synthetic-demo
```

The seed creates managers, conversations, encrypted messages, analysis findings,
CRM won/lost cases, follow-up tasks, outbox jobs, and metric snapshots through
real application services.

### 6. Start API

```bash
corepack pnpm run dev:api
```

### 7. Start worker

```bash
corepack pnpm run dev:worker
```

The root script runs `uv run closeros-worker all` (publisher + processor).

### 8. Start web

```bash
corepack pnpm run dev:web
```

### 9. Run HTTP smoke checks

```bash
export STAGING_API_URL=http://localhost:8000
export SMOKE_USER_EMAIL=owner@example.invalid
export SMOKE_USER_PASSWORD='<password from step 1>'
export SMOKE_EXPECTED_TENANT_ID=<TENANT_UUID>   # optional

uv run python scripts/ops/synthetic_smoke.py
```

Password must come from environment variables — never pass it on the command line.

Expected safe summary:

```json
{
  "status": "passed",
  "tenant_id": "...",
  "dashboard": "ok",
  "conversations": 6,
  "tasks": 2
}
```

### 10. Manual inspection

Sign in through the web UI and verify:

- Dashboard shows non-zero conversation metrics for the rolling window
- Conversations list and detail with evidence-backed findings
- Manager scorecards
- Open and completed follow-up tasks

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Bootstrap rejects user | Email not verified or user inactive |
| Dashboard empty | Metric window mismatch — smoke script aligns to tenant time zone rolling 30-day window |
| Conversation detail fails | Seed and API must share development encryption (`dev-kek-v1`) |
| Worker idle | Check `REDIS_URL`, run `dev:worker`, confirm outbox jobs in `outbox_jobs` |

## Related documentation

- `docs/ENVIRONMENT_VARIABLES.md`
- `docs/DEPLOYMENT.md`
- `docs/WORKER_OPERATIONS.md`
- `PROJECT_STATUS.md`
