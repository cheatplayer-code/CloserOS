# Deployment Overview

CloserOS uses remote-built container images, managed staging platform references,
and explicit operational release gates. Local development continues to use
`infra/docker/compose.yaml` for PostgreSQL and Redis only.

## Architecture (staging reference)

```text
Vercel          → Next.js web (@closeros/web)
Railway API     → FastAPI (infra/docker/Dockerfile.api)
Railway Worker  → outbox publisher/processor (Dockerfile.worker)
Railway Redis   → queue/cache (not source of truth)
Supabase        → managed PostgreSQL (migrations from this repo)
DeepSeek        → sanitized Reply Copilot context only during approved windows
```

PostgreSQL is the system of record. Redis carries outbox job UUIDs only. Vercel
is a presentation tier and receives no backend secrets.

## Container images

| Image | Dockerfile | Default process |
|-------|------------|-----------------|
| API | `infra/docker/Dockerfile.api` | `uvicorn closeros_api.app:app` |
| Worker | `infra/docker/Dockerfile.worker` | `closeros-worker all` |
| Web | `infra/docker/Dockerfile.web` | `node apps/web/server.js` (Next.js standalone) |

Images are built in GitHub Actions (`.github/workflows/containers.yml`) on every
PR and push to `master`. Images push to GHCR **only** on `v*` release tags.

Do **not** rely on local `docker build` in developer workflows unless debugging
image issues; CI is authoritative for remote builds, SBOM generation, and
vulnerability scanning.

## Staging release order

1. Merge only after quality, security, container, and Redis workflows are green.
2. Provision Supabase, Railway API/worker/Redis, and Vercel according to the
   platform runbooks.
3. Run `scripts/ops/staging_preflight.py --json` from a trusted operator shell.
4. Check Alembic status and apply a controlled migration if required.
5. Deploy API with `AI_EXTERNAL_CALLS_ENABLED=false`.
6. Require `GET /health` and `GET /ready` to return `200`.
7. Deploy worker and verify outbox processing.
8. Deploy web against the exact Railway API origin.
9. Bootstrap and seed fabricated staging data.
10. Pass synthetic baseline and disabled-provider smoke.
11. Seal the DeepSeek key, activate a bounded live window, and pass live/draft
    smoke.
12. Disable external AI and re-run the kill-switch smoke.
13. Rehearse rollback and store the private evidence bundle.

The authoritative S2 procedure is `docs/STAGING_SIGNOFF.md`.

## Pre-deploy checklist

1. `DATABASE_URL` targets Supabase direct or Shared Pooler **session mode** on
   port `5432` with TLS. The current runtime rejects transaction mode `6543`.
2. `REDIS_URL` uses Railway private networking with authentication or public TLS.
3. `STAGING_ENCRYPTION_KEY_HEX` and
   `STAGING_KNOWLEDGE_SEARCH_KEY_HEX` are separate sealed 64-hex values;
   `REDIS_RATE_LIMIT_HMAC_SECRET` and auth secrets are sealed and at least 32
   bytes.
4. `APP_ENV=staging` selects the managed staging path. It uses secure
   cookies, distributed rate limits, explicit provider gates, and sealed
   staging-only keys. `APP_ENV=production` remains remote-KMS-only.
5. `AI_EXTERNAL_CALLS_ENABLED=false` for baseline deployment.
6. Alembic is at head (`scripts/ops/migrate_status.py --json`).
7. Staging URLs are consistent across `STAGING_*`, `AUTH_ALLOWED_ORIGINS`, and
   `NEXT_PUBLIC_API_BASE_URL`.
8. CRM, messaging, SMTP, media, and production-only features remain disabled.
9. No real customer data or production credentials are present.
10. Staging preflight passes without warnings that require operator review.

## Platform guides

- `docs/STAGING_SIGNOFF.md` — exact S2 activation, evidence, kill-switch, rollback
- `docs/STAGING_SUPABASE.md` — PostgreSQL
- `docs/STAGING_RAILWAY.md` — API, worker, Redis
- `docs/STAGING_VERCEL.md` — web frontend
- `docs/STAGING_DEEPSEEK.md` — external AI (disabled by default)

## Operations

- `scripts/ops/staging_preflight.py` — non-secret environment consistency gate
- `scripts/ops/deepseek_staging_smoke.py` — live provider and kill-switch smoke
- `docs/SYNTHETIC_STAGING_SMOKE.md` — synthetic bootstrap, seed, and HTTP smoke
- `docs/MIGRATION_RUNBOOK.md`
- `docs/BACKUP_RESTORE.md`
- `docs/WORKER_OPERATIONS.md`
- `docs/INCIDENT_RESPONSE.md`
- `docs/SECRET_MANAGEMENT.md`
- `docs/OBSERVABILITY.md`
- `docs/ENVIRONMENT_VARIABLES.md`

## Production boundary

Passing S2 proves only a fabricated managed-staging deployment and live-provider
sandbox path. Production still requires approved Kazakhstan jurisdiction,
production KMS and key rotation, backup/restore evidence, continuous monitoring,
security/legal release approval, and a bounded design-partner pilot.

## CRM

First CRM target: Bitrix24 (overview in `docs/CRM_INTEGRATION.md`). It remains
disabled during S2.

## ADR

Accepted staging/production operations architecture:
`docs/adr/ADR-0017-production-operations-and-staging-architecture.md`.
