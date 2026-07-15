# S2 Managed Staging and DeepSeek Sign-off

This runbook activates the approved staging stack:

```text
Vercel          → Next.js web
Railway API     → FastAPI
Railway Worker  → outbox publisher + processor
Railway Redis   → queue/cache only
Supabase        → PostgreSQL source of truth
DeepSeek        → external AI for sanitized Reply Copilot context only
```

S2 proves the staging deployment and live provider path with fabricated data.
The services run with `APP_ENV=staging`: production-like HTTPS, cookies, rate
limits, feature gates, and fail-closed provider behavior, but sealed staging-only
static encryption/search keys. `APP_ENV=production` remains remote-KMS-only.
S2 does **not** authorize production traffic, real customer exports, autonomous
sending, or a production-readiness claim.

## Definition of done

S2 is signed off only when all of the following evidence exists:

- repository quality, security, container, and Redis workflows are green;
- Supabase migration status is at the repository head;
- Railway API returns `200` from `/health` and `/ready`;
- worker remains healthy and processes the synthetic outbox without dead letters;
- Vercel web authenticates against the exact Railway API origin;
- synthetic baseline smoke passes with external AI disabled;
- staging preflight passes without printing secrets;
- live DeepSeek smoke completes through the ordinary API composition;
- returned run metadata reports the expected provider, model, positive token
  counts, and positive latency;
- selecting a validated candidate creates an encrypted `draft` only;
- the external-AI kill switch is redeployed and verified;
- rollback to the last known-good deployment is rehearsed;
- no real or sensitive customer data is used.

Store command output in the private release record. Do not commit environment
exports, API keys, passwords, database URLs, response text, prompts, or cookies.

## 1. Provision Supabase PostgreSQL

1. Create a dedicated **staging** project in the approved temporary staging
   region. This is not a production jurisdiction decision.
2. Create a strong database password in the password manager.
3. For the persistent Railway API and worker, choose one of:
   - direct connection on port `5432` when Railway can reach the Supabase IPv6
     endpoint; or
   - Shared Pooler **session mode** on port `5432` when an IPv4-compatible
     connection is required.
4. Append `sslmode=require` or a stronger TLS verification mode.
5. Do not use Shared Pooler transaction mode on port `6543` with the current
   SQLAlchemy/psycopg runtime. Transaction mode does not support prepared
   statements and is intended for transient serverless connections.
6. Store the resulting URL as sealed/shared `DATABASE_URL` for Railway API and
   worker. Never put it in Vercel or GitHub.

Read-only migration status:

```bash
uv run python scripts/ops/migrate_status.py --json
```

Controlled staging upgrade:

```bash
uv run python scripts/ops/migrate_upgrade.py --confirm
uv run python scripts/ops/migrate_status.py --json
```

The status command must return `pending_upgrade: false` before application
rollout.

## 2. Provision Railway services

Create one Railway project with a staging environment and three services.

### API service

- source: this GitHub repository, branch `master`;
- config path: `infra/railway/railway.api.toml`;
- healthcheck path: `/ready`;
- public HTTPS domain enabled;
- one replica for staging.

Railway injects `PORT`; the API container already binds to it. `/ready` checks
required database connectivity, while `/health` is liveness only.

### Worker service

- source: this GitHub repository, branch `master`;
- config path: `infra/railway/railway.worker.toml`;
- one replica;
- no public domain;
- monitor logs, outbox lag, retry count, and dead-letter count.

### Redis service

Use Railway's managed Redis template. Keep it private. Reference its authenticated
private URL from API and worker. If traffic leaves Railway private networking,
use a TLS `rediss://` endpoint instead.

### Shared Railway variables

Set these on API and worker where applicable:

```text
APP_ENV=staging
DATABASE_URL=<sealed Supabase direct/session URL>
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

API-only variables:

```text
STAGING_API_URL=https://<railway-api-domain>
STAGING_WEB_URL=https://<vercel-staging-domain>
AUTH_ALLOWED_ORIGINS=https://<vercel-staging-domain>
NEXT_PUBLIC_API_BASE_URL=https://<railway-api-domain>
AI_EXTERNAL_CALLS_ENABLED=false
DEEPSEEK_BASE_URL=https://api.deepseek.com/
DEEPSEEK_MODEL=deepseek-v4-flash
```

`DEEPSEEK_API_KEY` is added later and sealed before live activation. Railway
sealed variables are available to deployments but cannot be read back from the
UI or API. They are not copied automatically to PR environments or duplicated
services, so verify each environment explicitly.

## 3. Provision Vercel web

- import this repository;
- use `infra/vercel/vercel.json`;
- keep the repository root as the project root;
- set `NEXT_PUBLIC_API_BASE_URL` to the exact Railway API HTTPS origin;
- do not add database, Redis, encryption, authentication-secret, or DeepSeek
  credentials to Vercel;
- create a stable staging domain and add that exact origin to
  `AUTH_ALLOWED_ORIGINS` on Railway;
- redeploy after any environment-variable change because Vercel variables apply
  only to new deployments.

Do not point arbitrary preview deployments at the shared staging database. Use a
fixed staging hostname or branch-scoped preview variables.

## 4. Baseline deployment with external AI disabled

Deploy API, worker, and web with:

```text
AI_EXTERNAL_CALLS_ENABLED=false
```

Verify:

```bash
curl --fail --silent --show-error "$STAGING_API_URL/health"
curl --fail --silent --show-error "$STAGING_API_URL/ready"
```

Railway waits for an HTTP `200` from the configured healthcheck before making a
new deployment active. Railway healthchecks are deployment gates, not continuous
monitoring; configure separate uptime monitoring after activation.

Run the fail-closed environment check from a trusted operator shell whose
environment contains the staging variables:

```bash
uv run python scripts/ops/staging_preflight.py --json
```

The command prints statuses and metadata only. It never prints secret values.

## 5. Bootstrap fabricated staging data

Follow `docs/SYNTHETIC_STAGING_SMOKE.md`:

1. register and verify an `example.invalid` smoke user;
2. run migrations;
3. bootstrap the first tenant;
4. seed the synthetic demo graph;
5. run the baseline HTTP smoke.

```bash
uv run python scripts/ops/synthetic_smoke.py
```

No real customer names, phone numbers, message bodies, exports, or production
credentials are allowed in S2.

## 6. Verify the kill switch before live activation

With external AI still disabled, set only operator-side smoke credentials:

```text
STAGING_API_URL=https://<railway-api-domain>
STAGING_WEB_URL=https://<vercel-staging-domain>
SMOKE_USER_EMAIL=<synthetic user>
SMOKE_USER_PASSWORD=<password-manager value>
SMOKE_EXPECTED_TENANT_ID=<tenant UUID>
```

Run:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py --expect-disabled
```

Expected evidence:

- run status `blocked`;
- failure code `provider_failure`;
- provider and model are absent;
- zero candidates;
- no draft is created.

This verifies the product-level disabled behavior. Railway/DeepSeek logs and
provider usage must show no external call for the test window.

## 7. Enable live DeepSeek

1. Add `DEEPSEEK_API_KEY` to the Railway API service.
2. Seal the variable immediately.
3. Set:

```text
AI_EXTERNAL_CALLS_ENABLED=true
DEEPSEEK_BASE_URL=https://api.deepseek.com/
DEEPSEEK_MODEL=deepseek-v4-flash
```

4. Review and deploy the staged variable changes.
5. Confirm `/ready` remains `200`.
6. Re-run preflight:

```bash
uv run python scripts/ops/staging_preflight.py --json
```

The API fails startup closed if the key or model is missing, or if the base URL
is not HTTPS. It never silently falls back to synthetic output in the production
runtime path.

## 8. Run live DeepSeek acceptance

Run once without candidate selection:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py
```

Then run once with encrypted draft verification:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py --select-candidate
```

The safe JSON summary contains identifiers and non-sensitive telemetry only. It
must show:

```text
mode=live
provider_code=openai
model_code=deepseek-v4-flash
input_tokens>0
output_tokens>0
latency_milliseconds>0
candidate_count>0
draft_created=true  # on the second command
```

The script never prints candidate text, prompts, output bodies, cookies, CSRF
tokens, passwords, or the DeepSeek key.

Manually confirm in the web UI that:

- generated candidates are grounded in the synthetic conversation;
- evidence references point to messages from the same tenant and thread;
- no unsupported discount, promise, URL, or sensitive field appears;
- the selected candidate remains an outbound `draft` requiring explicit human
  approval;
- no provider message is sent automatically.

## 9. Disable and re-verify the kill switch

Set `AI_EXTERNAL_CALLS_ENABLED=false`, deploy, and run:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py --expect-disabled
```

Confirm no new DeepSeek usage for the test window. This is the mandatory
operator kill-switch drill.

After evidence is captured, keep external AI disabled unless an approved staging
session is active.

## 10. Rollback drill

1. Record the active API, worker, and web deployment identifiers.
2. Redeploy the previous known-good API deployment or revert the staging branch
   deployment.
3. Verify `/health`, `/ready`, login, synthetic smoke, and worker processing.
4. Restore the S2 deployment and repeat readiness checks.
5. Record timestamps, deployment IDs, and result only; never record secrets.

## Required private evidence bundle

The release record should contain:

- Git commit SHA and green workflow links;
- Supabase project region and connection mode, without URI or credentials;
- migration status JSON;
- staging preflight JSON;
- synthetic smoke JSON;
- disabled smoke JSON before live activation;
- live smoke JSON;
- draft-creation smoke JSON;
- disabled smoke JSON after live activation;
- API `/ready` result and worker health evidence;
- Railway/Vercel deployment IDs;
- rollback drill result;
- DeepSeek usage screenshot or export with customer content excluded.

## Failure handling

| Failure | Required action |
|---------|-----------------|
| Preflight fails | Do not deploy; fix configuration first |
| `/ready` not `200` | Keep previous deployment active; inspect DB connectivity |
| Migration pending | Stop rollout; run controlled migration procedure |
| Provider/model mismatch | Disable external AI and investigate composition/configuration |
| Zero or missing telemetry | Disable external AI; verify provider response persistence |
| Invalid or ungrounded output | Disable external AI; preserve run ID and request ID only |
| Candidate selection sends a message | Critical incident; disable worker/provider and follow incident runbook |
| DeepSeek outage/rate limit | Disable external AI; synthetic fallback is forbidden in production |

## Related documentation

- `docs/DEPLOYMENT.md`
- `docs/STAGING_SUPABASE.md`
- `docs/STAGING_RAILWAY.md`
- `docs/STAGING_VERCEL.md`
- `docs/STAGING_DEEPSEEK.md`
- `docs/SYNTHETIC_STAGING_SMOKE.md`
- `docs/MIGRATION_RUNBOOK.md`
- `docs/INCIDENT_RESPONSE.md`
- `docs/SECRET_MANAGEMENT.md`
