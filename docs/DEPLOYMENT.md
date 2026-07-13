# Deployment Overview

Block XY introduces remote-build container images, staging platform references,
and operational runbooks. Local development continues to use `infra/docker/compose.yaml`
for PostgreSQL and Redis only.

## Architecture (staging reference)

```text
Vercel          → Next.js web (@closeros/web)
Railway API     → FastAPI (infra/docker/Dockerfile.api)
Railway Worker  → outbox publisher/processor (Dockerfile.worker)
Railway Redis   → queue/cache (not source of truth)
Supabase        → managed PostgreSQL (migrations from this repo)
```

PostgreSQL is the system of record. Redis carries outbox job UUIDs only.

## Container images

| Image | Dockerfile | Default process |
|-------|------------|-----------------|
| API | `infra/docker/Dockerfile.api` | `uvicorn closeros_api.app:app` |
| Worker | `infra/docker/Dockerfile.worker` | `closeros-worker all` |
| Web | `infra/docker/Dockerfile.web` | `node apps/web/server.js` (Next.js standalone) |

Images are built in GitHub Actions (`.github/workflows/containers.yml`) on every
PR and push to `master`. Images push to GHCR **only** on `v*` release tags.

Do **not** rely on local `docker build` in developer workflows unless debugging
image issues; CI is authoritative for remote builds.

## Pre-deploy checklist

1. `DATABASE_URL` points at Supabase pooler with TLS.
2. `REDIS_URL` points at managed Redis with password/TLS.
3. `APP_ENCRYPTION_KEY` and auth secrets meet production length requirements.
4. `AI_EXTERNAL_CALLS_ENABLED=false` until legal and budget gates pass.
5. Alembic at head (`scripts/ops/migrate_status.py`).
6. Staging URLs configured in `AUTH_ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL`.
7. CRM and messaging credentials stored as platform secrets, not in git.

## Platform guides

- `docs/STAGING_SUPABASE.md` — PostgreSQL
- `docs/STAGING_RAILWAY.md` — API, worker, Redis
- `docs/STAGING_VERCEL.md` — web frontend
- `docs/STAGING_DEEPSEEK.md` — external AI (disabled by default)

## Operations

- `docs/SYNTHETIC_STAGING_SMOKE.md` — synthetic bootstrap, seed, and HTTP smoke (no live providers)
- `docs/MIGRATION_RUNBOOK.md`
- `docs/BACKUP_RESTORE.md`
- `docs/WORKER_OPERATIONS.md`
- `docs/INCIDENT_RESPONSE.md`
- `docs/SECRET_MANAGEMENT.md`
- `docs/OBSERVABILITY.md`
- `docs/ENVIRONMENT_VARIABLES.md`

## CRM

First CRM target: Bitrix24 (overview in `docs/CRM_INTEGRATION.md`).

## ADR

Accepted staging/production operations architecture:
`docs/adr/ADR-0017-production-operations-and-staging-architecture.md`.
