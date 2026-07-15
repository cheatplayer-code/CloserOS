# Environment Variables

Canonical reference for CloserOS configuration. Safe defaults live in
`.env.example`. Production and staging values are injected through platform
secret stores.

## Core

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `APP_ENV` | yes | `development`, `staging`, or `production`. Managed staging uses `staging`; production remains remote-KMS-only. |
| `APP_NAME` | no | Log label (`closeros`) |
| `LOG_LEVEL` | no | `INFO` default |

## Database and cache

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `DATABASE_URL` | yes | Supabase direct or Shared Pooler **session mode** URI on port `5432` with `sslmode=require` or stronger. Current staging preflight rejects transaction mode `6543`. |
| `TEST_DATABASE_URL` | CI only | Maintenance DB for pytest fixtures |
| `REDIS_URL` | yes (worker/API as needed) | Authenticated Railway private `redis://` URL or public `rediss://` URL |
| `REDIS_PASSWORD` | local compose | Local infra only |
| `REDIS_RATE_LIMIT_ENABLED` | no | `true` to enforce Redis-backed auth rate limits |
| `REDIS_RATE_LIMIT_PREFIX` | no | Key prefix, default `closeros:ratelimit` |

## Authentication (API)

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `AUTH_ALLOWED_ORIGINS` | yes | Comma-separated exact HTTPS origins; wildcards forbidden for staging |
| `AUTH_CSRF_SECRET` | yes | At least 32 bytes in production/staging; seal in Railway |
| `AUTH_RATE_LIMIT_SECRET` | yes | At least 32 bytes in production/staging; seal in Railway |
| `AUTH_SESSION_TOUCH_MINUTES` | no | Session refresh interval |
| `AUTH_TRUST_FORWARDED_CLIENT_IP` | no | `true` behind trusted proxy only |

## Staging URLs

| Variable | Required (staging) | Description |
|----------|-------------------|-------------|
| `STAGING_API_URL` | yes | Exact public HTTPS API origin on Railway |
| `STAGING_WEB_URL` | yes | Exact stable HTTPS web origin on Vercel |
| `NEXT_PUBLIC_API_BASE_URL` | yes (web build) | Must exactly match `STAGING_API_URL`; embedded in browser bundle |

## Encryption and KMS

| Variable | Required | Description |
|----------|----------|-------------|
| `STAGING_ENCRYPTION_KEY_HEX` | staging | Sealed 64-hex (32-byte) staging-only KEK. Never reuse in production. |
| `STAGING_ENCRYPTION_KEY_VERSION` | staging | Explicit staging key version, for example `staging-kek-v1`. |
| `STAGING_KNOWLEDGE_SEARCH_KEY_HEX` | staging | Separate sealed 64-hex key for deterministic lexical-search tokens. |
| `REDIS_RATE_LIMIT_HMAC_SECRET` | staging/production | Sealed HMAC secret of at least 32 bytes for distributed authentication rate-limit keys. |
| `KMS_BASE_URL` | production KMS | HTTPS base URL for remote KMS adapter |
| `KMS_API_TOKEN_REF` | production KMS | Secret reference for KMS API token (e.g. `env:KMS_API_TOKEN`) |
| `KMS_ACTIVE_KEY_VERSION` | production KMS | Active key encryption key version id |
| `KMS_KEY_VERSIONS` | production KMS | Comma-separated KEK versions known to the runtime |
| `KNOWLEDGE_SEARCH_KEY_REF` | production | Secret reference for knowledge lexical search key |
| `KNOWLEDGE_SEARCH_KEY_VERSION` | no | Search key version label (default from code) |
| `CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX` | dev only | Deterministic 64-hex dev search key |

## Optional production feature gates

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_ENABLED` | `false` | Register WhatsApp Cloud webhook adapter |
| `CRM_ENABLED` | `false` | Enable CRM sync handlers |
| `NOTIFICATIONS_ENABLED` | `false` | Enable SMTP notification delivery |
| `MEDIA_SCANNER_ENABLED` | `false` | Enable ClamAV media scanning pipeline |

All optional integrations remain `false` during S2 unless separately approved.

## Worker / outbox

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `WORKER_ID` | recommended | Unique replica id |
| `WORKER_POLLING_INTERVAL_SECONDS` | no | Publisher interval |
| `WORKER_PUBLISH_BATCH_SIZE` | no | Publisher batch |
| `WORKER_PROCESSOR_BLOCK_MS` | no | Redis block timeout |
| `OUTBOX_STREAM` | no | Redis stream name |
| `OUTBOX_CONSUMER_GROUP` | no | Consumer group name |

## Ingestion

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `INGESTION_SERVICE_ID` | yes | UUID for ingestion audit identity |
| `WEBHOOK_MAX_BODY_BYTES` | no | Webhook size cap |
| `CSV_MAX_BODY_BYTES` | no | CSV upload cap |
| `SYNTHETIC_WEBHOOK_SECRET` | dev only | JK synthetic adapter |

## External AI (disabled default)

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_EXTERNAL_CALLS_ENABLED` | no | `false` by default. Development uses deterministic synthetic replies while disabled; production/staging does not silently fall back to synthetic AI. |
| `DEEPSEEK_API_KEY` | if enabled | Vendor key injected into Railway API only for S2 Reply Copilot. Seal it; hidden from settings repr and never persisted. |
| `DEEPSEEK_BASE_URL` | if enabled | HTTPS OpenAI-compatible base. Defaults to `https://api.deepseek.com/`. Credentials, query strings, and fragments are rejected. |
| `DEEPSEEK_MODEL` | if enabled | Explicit reviewed model code: `deepseek-v4-flash` or `deepseek-v4-pro`. Deprecated aliases are rejected by S2 preflight. |
| `OPENAI_COMPATIBLE_*` | optional | Alternate provider variables used by other gateway paths; not the Reply Copilot source of truth. |
| `CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX` | dev only | Deterministic dev search. |

When `AI_EXTERNAL_CALLS_ENABLED=true`, API startup fails closed unless the key,
HTTPS base URL, and model are valid. No external request is attempted while the
flag is disabled.

## Staging preflight and smoke (Z0/S2)

| Variable | Required | Description |
|----------|----------|-------------|
| `STAGING_API_URL` | preflight/smoke | Exact Railway API HTTPS origin |
| `STAGING_WEB_URL` | preflight/DeepSeek smoke | Exact Vercel origin used for CSRF `Origin` checks |
| `SMOKE_USER_EMAIL` | smoke scripts | Fabricated verified test-user email |
| `SMOKE_USER_PASSWORD` | smoke scripts | Password from environment only; never CLI flag or Git |
| `SMOKE_EXPECTED_TENANT_ID` | optional | Expected fabricated tenant UUID |
| `SMOKE_CONVERSATION_THREAD_ID` | optional | Specific seeded synthetic thread UUID |
| `SMOKE_EXPECTED_AI_PROVIDER` | optional | Defaults to `openai` for live DeepSeek smoke |
| `SMOKE_EXPECTED_AI_MODEL` | optional | Defaults to `DEEPSEEK_MODEL` or `deepseek-v4-flash` |

Operator commands:

```bash
corepack pnpm staging:preflight
corepack pnpm staging:smoke:synthetic
corepack pnpm staging:smoke:deepseek:disabled
corepack pnpm staging:smoke:deepseek
corepack pnpm staging:smoke:deepseek:draft
```

Smoke summaries contain identifiers and non-sensitive telemetry only. Do not
store environment exports, passwords, cookies, candidate text, prompts, model
output bodies, or complete connection URLs in release evidence.

## WhatsApp (VW)

| Variable | Required when connected | Description |
|----------|-------------------------|-------------|
| `WHATSAPP_GRAPH_API_VERSION` | yes | e.g. `v21.0` |
| `WHATSAPP_ACCESS_TOKEN` | yes | Resolved via ref in prod |
| `WHATSAPP_APP_SECRET` | yes | Webhook HMAC |
| `WHATSAPP_VERIFY_TOKEN` | yes | Hub verification |

## CRM — Bitrix24 (XY)

Runtime production checks use portal domain and access-token references (not OAuth
client env vars on the worker hot path):

| Variable | Required when `CRM_ENABLED=true` | Description |
|----------|--------------------------------|-------------|
| `BITRIX24_PORTAL_DOMAIN` | yes | Tenant portal host (SSRF-validated) |
| `BITRIX24_ACCESS_TOKEN_REF` | yes | Secret reference for inbound API token |

Per-tenant OAuth and webhook configuration is stored in tenant-scoped connection
rows. See `docs/CRM_INTEGRATION.md` for adapter behavior.

## Email (SMTP)

| Variable | Required when `NOTIFICATIONS_ENABLED=true` | Description |
|----------|--------------------------------------------|-------------|
| `SMTP_HOST` | yes | SMTP server hostname |
| `SMTP_PORT` | yes | SMTP port |
| `SMTP_FROM_ADDRESS` | yes | From address |
| `SMTP_USERNAME_REF` | optional | Secret reference for SMTP username |
| `SMTP_PASSWORD_REF` | optional | Secret reference for SMTP password |
| `SMTP_TRANSPORT` | no | `starttls` (default) or `tls` |

## Media scanning (placeholders)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_SCANNER_ENABLED` | `false` | Gate media pipeline |
| `MEDIA_OBJECT_STORE_BUCKET` | blank | Future object store |
| `MEDIA_OBJECT_STORE_REGION` | blank | Object store region |

## Related documentation

- `.env.example`
- `docs/SECRET_MANAGEMENT.md`
- `docs/STAGING_SIGNOFF.md`
- `docs/STAGING_SUPABASE.md`
- `docs/STAGING_RAILWAY.md`
- `docs/STAGING_VERCEL.md`
- `docs/STAGING_DEEPSEEK.md`
- `docs/SYNTHETIC_STAGING_SMOKE.md`
