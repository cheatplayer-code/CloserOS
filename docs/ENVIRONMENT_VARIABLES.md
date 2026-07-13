# Environment Variables

Canonical reference for CloserOS configuration. Safe defaults live in
`.env.example`. Production values are injected through platform secret stores.

## Core

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `APP_ENV` | yes | `development` or `production` |
| `APP_NAME` | no | Log label (`closeros`) |
| `LOG_LEVEL` | no | `INFO` default |

## Database and cache

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `DATABASE_URL` | yes | PostgreSQL URI (Supabase pooler in staging) |
| `TEST_DATABASE_URL` | CI only | Maintenance DB for pytest fixtures |
| `REDIS_URL` | yes (worker/API as needed) | Redis URI with auth |
| `REDIS_PASSWORD` | local compose | Local infra only |
| `REDIS_RATE_LIMIT_ENABLED` | no | `true` to enforce Redis-backed auth rate limits |
| `REDIS_RATE_LIMIT_PREFIX` | no | Key prefix, default `closeros:ratelimit` |

## Authentication (API)

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `AUTH_ALLOWED_ORIGINS` | yes | Comma-separated HTTPS origins |
| `AUTH_CSRF_SECRET` | yes | ≥32 bytes in production |
| `AUTH_RATE_LIMIT_SECRET` | yes | ≥32 bytes in production |
| `AUTH_SESSION_TOUCH_MINUTES` | no | Session refresh interval |
| `AUTH_TRUST_FORWARDED_CLIENT_IP` | no | `true` behind trusted proxy only |

## Staging URLs

| Variable | Required (staging) | Description |
|----------|-------------------|-------------|
| `STAGING_API_URL` | yes | Public API base (Railway) |
| `STAGING_WEB_URL` | yes | Public web origin (Vercel) |
| `NEXT_PUBLIC_API_BASE_URL` | yes (web build) | Same as staging API URL |

## Encryption and KMS

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_ENCRYPTION_KEY` | development / transitional | Local envelope encryption key material. Development API/worker composition and operator scripts use deterministic `dev-kek-v1` when unset. **Not** a substitute for production remote KMS. |
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
| `AI_EXTERNAL_CALLS_ENABLED` | no | `false` default |
| `DEEPSEEK_API_KEY` | if enabled | Vendor key (blank default) |
| `DEEPSEEK_BASE_URL` | if enabled | HTTPS OpenAI-compatible base |
| `OPENAI_COMPATIBLE_*` | optional | Alternate provider |
| `CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX` | dev only | Deterministic dev search |

## Synthetic staging smoke (Z0)

| Variable | Required | Description |
|----------|----------|-------------|
| `STAGING_API_URL` | smoke script | Public API base URL |
| `SMOKE_USER_EMAIL` | smoke script | Synthetic test user email |
| `SMOKE_USER_PASSWORD` | smoke script | Password (env only — never CLI flag) |
| `SMOKE_EXPECTED_TENANT_ID` | optional | Expected tenant UUID |

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
- `docs/STAGING_DEEPSEEK.md`
- `docs/CRM_INTEGRATION.md`
- `docs/SYNTHETIC_STAGING_SMOKE.md`
