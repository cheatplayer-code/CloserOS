# ADR-0017: Production operations and staging architecture

Status: Accepted
Date: 2026-07-12
Documentation review date: 2026-07-12

## Context

Blocks FG–VW delivered the modular monolith application code, encrypted storage,
outbox processing, AI gateway, product workspace, and WhatsApp Cloud adapter.
Block XY must enable **staging operations** without claiming Block Z production
release-gate completion.

Constraints:

- PostgreSQL remains the source of truth; Redis is queue/cache only.
- No local Docker builds as a developer requirement; images build in CI.
- Kazakhstan production jurisdiction is targeted but provider selection is not
  final; staging may use internationally available PaaS documented here.
- Supabase provides PostgreSQL only — not Supabase Auth.
- External AI and CRM credentials stay disabled until explicit enablement.
- No autonomous outbound messaging.

## Decision

### Staging topology

| Layer | Platform | Artifact |
|-------|----------|----------|
| Web | Vercel | Next.js monorepo build (`@closeros/web`) |
| API | Railway | `infra/docker/Dockerfile.api` |
| Worker | Railway | `infra/docker/Dockerfile.worker` |
| Redis | Railway managed Redis | `infra/railway/railway.redis.toml` |
| PostgreSQL | Supabase | Migrations from repository |

Config-as-code:

- `infra/railway/railway.api.toml`
- `infra/railway/railway.worker.toml`
- `infra/vercel/vercel.json`
- `infra/supabase/README.md`

Reference-only compose: `infra/docker/docker-compose.staging.yml.example`.

### Container build and supply chain

- Multi-stage Dockerfiles for API, worker, and web; non-root runtime users.
- Root `.dockerignore` excludes tests, docs, and local compose.
- GitHub Actions `containers.yml` builds on `ubuntu-24.04`, generates SPDX SBOMs
  (Anchore syft action), scans with Trivy (fail on CRITICAL/HIGH unfixed).
- Images load locally in CI; push to GHCR occurs **only** on `v*` tags.

### CI extensions

- Dedicated `redis-integration` job in `quality.yml` running `pytest -m redis_integration`.
- Pinned third-party action SHAs; `contents: read` default.

### Operations tooling

Python and shell wrappers under `scripts/ops/`:

- `migrate_status.py` / `migrate_upgrade.py` with non-local `--confirm` gates;
- `backup_pg.sh` / `restore_pg.sh` dry-run by default.

Worker operations documented in `docs/WORKER_OPERATIONS.md`.

### CRM

Bitrix24 is the first CRM integration target (`docs/CRM_INTEGRATION.md`).
Outcome authority remains with CRM (ADR-0004).

### Secrets and encryption

- Platform secret stores for staging; reference keys in PostgreSQL for connections.
- `APP_ENCRYPTION_KEY` for envelope encryption until KMS adapter passes Block Z.
- KMS variables documented but adapter not enabled in XY.

### Explicit non-goals (deferred to Block Z)

- Production jurisdiction sign-off and paid pilot release gate.
- Live Meta sandbox verification completion.
- Media malware scanning pipeline.
- Production KMS and object storage adapters.
- Autonomous outbound messaging.
- Legal hold automation UI.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| Single Dockerfile for all processes | Violates least privilege and independent scaling |
| Kubernetes staging | ADR-0001 modular monolith; no proven need |
| Supabase Auth | Conflicts with ADR-0010 self-hosted sessions |
| Local docker-compose staging | Does not match operator PaaS workflow; secrets risk |
| Push every CI build to registry | Supply-chain noise; tag-gated push only |

## Consequences

- Operators can provision staging from documented PaaS steps without local Docker.
- CI time increases due to image builds and scans.
- Production hosting may differ from staging; ADR update required before prod.
- CRM adapter implementation can proceed against stable deployment docs.

## Security and privacy impact

- Container images run as non-root; health checks avoid logging secrets.
- Trivy blocks CRITICAL/HIGH unfixed CVEs in CI.
- Migration and restore scripts refuse known dev credential markers by default.
- Staging URLs and CRM secrets are never committed.

## Migration and rollback/remediation

- Schema: forward-only Alembic (`docs/MIGRATION_RUNBOOK.md`).
- Deploy: roll back Railway/Vercel to previous successful deployment.
- Data: restore from Supabase/operator backup (`docs/BACKUP_RESTORE.md`).

## Sources verified

- Railway config-as-code reference — 2026-07-12 — https://docs.railway.com/config-as-code
- Vercel monorepo guidance — 2026-07-12 — https://vercel.com/docs
- Supabase connection pooling — 2026-07-12 — https://supabase.com/docs/guides/database/connecting-to-postgres
- Anchore sbom-action — 2026-07-12 — https://github.com/anchore/sbom-action
- Aqua Trivy action — 2026-07-12 — https://github.com/aquasecurity/trivy-action
