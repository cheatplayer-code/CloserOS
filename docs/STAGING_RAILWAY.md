# Staging — Railway (API, Worker, Redis)

Railway hosts the CloserOS API, background worker, and managed Redis for staging.
The complete activation order and evidence requirements are in
`docs/STAGING_SIGNOFF.md`.

Config-as-code files:

- `infra/railway/railway.api.toml`
- `infra/railway/railway.worker.toml`
- `infra/railway/railway.redis.toml`

Point each Railway service at the matching config file path in the repository.
Use a dedicated staging environment; do not copy sealed variables into preview
services manually unless that preview is explicitly approved.

## Services

### API

- Builder: `DOCKERFILE` → `infra/docker/Dockerfile.api`
- Health check: `GET /ready` (required database connectivity)
- Liveness: `GET /health`
- Public HTTPS domain enabled
- One replica for staging
- Required variables: `DATABASE_URL`, `REDIS_URL`, `AUTH_*`,
  `STAGING_ENCRYPTION_KEY_HEX`, `STAGING_KNOWLEDGE_SEARCH_KEY_HEX`,
  `REDIS_RATE_LIMIT_HMAC_SECRET`, `INGESTION_SERVICE_ID`, and
  `AUTH_ALLOWED_ORIGINS`

Railway injects `PORT`; the image binds `0.0.0.0:${PORT}`. Railway makes a new
deployment active only after the configured healthcheck returns HTTP `200`.
Railway deployment healthchecks are not continuous monitoring, so configure a
separate uptime check after activation.

### Worker

- Builder: `DOCKERFILE` → `infra/docker/Dockerfile.worker`
- Start command: `closeros-worker all` (publisher + processor)
- No public domain
- One replica for staging
- Same `DATABASE_URL`, `REDIS_URL`, and encryption/KMS configuration as API
- Monitor logs, outbox lag, retries, and dead-letter counts

Scale worker replicas only after lag monitoring exists
(`docs/WORKER_OPERATIONS.md`).

### Redis

- Use Railway Redis template or equivalent managed Redis
- Keep the service on Railway private networking
- Require authentication
- Use the authenticated private `redis://` URL only inside Railway private
  networking; use `rediss://` if traffic leaves that network
- Set the same `REDIS_URL` on API and worker
- Redis is delivery/cache only and is not a source of truth

## Variables

Shared API/worker staging variables:

```text
APP_ENV=staging
DATABASE_URL=<sealed Supabase direct/session URL on port 5432 with TLS>
REDIS_URL=<authenticated Railway Redis URL>
STAGING_ENCRYPTION_KEY_HEX=<sealed random 64-hex value>
STAGING_ENCRYPTION_KEY_VERSION=staging-kek-v1
STAGING_KNOWLEDGE_SEARCH_KEY_HEX=<sealed random 64-hex value>
REDIS_RATE_LIMIT_HMAC_SECRET=<sealed random value, at least 32 bytes>
AUTH_CSRF_SECRET=<sealed random value, at least 32 bytes>
AUTH_RATE_LIMIT_SECRET=<sealed random value, at least 32 bytes>
INGESTION_SERVICE_ID=<staging UUID>
WHATSAPP_ENABLED=false
CRM_ENABLED=false
NOTIFICATIONS_ENABLED=false
MEDIA_SCANNER_ENABLED=false
```

API-only staging variables:

```text
STAGING_API_URL=https://<railway-api-domain>
STAGING_WEB_URL=https://<vercel-staging-domain>
AUTH_ALLOWED_ORIGINS=https://<vercel-staging-domain>
NEXT_PUBLIC_API_BASE_URL=https://<railway-api-domain>
AI_EXTERNAL_CALLS_ENABLED=false
DEEPSEEK_BASE_URL=https://api.deepseek.com/
DEEPSEEK_MODEL=deepseek-v4-flash
```

Add `DEEPSEEK_API_KEY` only during the approved live-provider window. Seal it
immediately. Railway sealed values are supplied to deployments but cannot be
read back through the UI or API. They are not copied automatically to PR
environments, duplicated environments, or duplicated services.

## Deploy flow

1. Merge a green commit to `master`; CI builds and scans images.
2. Run `scripts/ops/staging_preflight.py --json` from a trusted operator shell.
3. Check migration status and apply any controlled migration before application
   rollout.
4. Deploy API with external AI disabled.
5. Verify `/health` and `/ready` return `200`.
6. Deploy worker and verify stable logs/outbox processing.
7. Deploy Vercel web against the exact Railway API origin.
8. Bootstrap and seed fabricated staging data.
9. Run synthetic baseline smoke.
10. Run disabled DeepSeek smoke.
11. Seal the DeepSeek key, enable external AI, deploy, and run live smoke.
12. Disable external AI again and repeat the kill-switch smoke.
13. Rehearse rollback and capture private evidence.

## Networking

- API receives browser traffic and approved provider webhooks over HTTPS.
- Restrict admin routes to authenticated sessions only.
- Do not expose Redis publicly.
- Prefer Supabase direct or Shared Pooler session mode on port `5432`; the
  transaction pooler on `6543` is rejected by staging preflight.
- If host allow-lists are enabled, permit Railway's healthcheck host and required
  provider egress without weakening authentication.

## Secrets

Inject secrets through Railway variables or a linked secrets manager. Seal
high-value variables after validation. See `docs/SECRET_MANAGEMENT.md`.
Never store tokens, passwords, complete connection URLs, or encryption keys in
Git, command history, CI logs, issue comments, or smoke evidence.

## Verification commands

```bash
uv run python scripts/ops/staging_preflight.py --json
uv run python scripts/ops/migrate_status.py --json
uv run python scripts/ops/synthetic_smoke.py
uv run python scripts/ops/deepseek_staging_smoke.py --expect-disabled
uv run python scripts/ops/deepseek_staging_smoke.py
uv run python scripts/ops/deepseek_staging_smoke.py --select-candidate
```

## Reference compose

`infra/docker/docker-compose.staging.yml.example` documents a non-secret topology
for operators. It is not executed in CI and must not contain real credentials.
