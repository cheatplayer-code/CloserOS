# Staging — Railway (API, Worker, Redis)

Railway hosts the CloserOS API, background worker, and managed Redis for staging.

Config-as-code files:

- `infra/railway/railway.api.toml`
- `infra/railway/railway.worker.toml`
- `infra/railway/railway.redis.toml`

Point each Railway service at the matching config file path in the repository.

## Services

### API

- Builder: `DOCKERFILE` → `infra/docker/Dockerfile.api`
- Health check: `GET /ready` (database connectivity)
- Liveness: `GET /health`
- Required variables: `DATABASE_URL`, `REDIS_URL`, `AUTH_*`, `APP_ENCRYPTION_KEY`,
  `INGESTION_SERVICE_ID`, `AUTH_ALLOWED_ORIGINS`

Railway injects `PORT`; the image binds `0.0.0.0:${PORT}`.

### Worker

- Builder: `DOCKERFILE` → `infra/docker/Dockerfile.worker`
- Start command: `closeros-worker all` (publisher + processor)
- No HTTP health endpoint — monitor logs and outbox lag
- Same `DATABASE_URL`, `REDIS_URL`, and encryption secrets as API

Scale worker replicas only after lag monitoring exists (`docs/WORKER_OPERATIONS.md`).

### Redis

- Use Railway Redis template or equivalent managed Redis
- Enable password authentication and TLS in staging/production
- Set `REDIS_URL` on API and worker (not a source of truth)

## Deploy flow

1. Merge to `master`; CI builds and scans images (`containers.yml`).
2. Railway watches the linked branch and rebuilds from Dockerfile.
3. Run migrations if schema changed (`docs/MIGRATION_RUNBOOK.md`).
4. Deploy API, then worker, then verify `/ready` and worker logs.

## Networking

- API receives webhooks from Meta and future CRM providers over HTTPS.
- Restrict admin routes to authenticated sessions only.
- Do not expose Redis publicly.

## Secrets

Inject through Railway variables or a linked secrets manager. See
`docs/SECRET_MANAGEMENT.md`. Never store tokens in the repository.

## Reference compose

`infra/docker/docker-compose.staging.yml.example` documents a non-secret topology
for operators. It is not executed in CI and must not contain real credentials.
