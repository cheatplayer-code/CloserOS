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

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `APP_ENCRYPTION_KEY` | yes | Local envelope encryption key |
| `KMS_PROVIDER` | no | Future KMS adapter id |
| `KMS_KEY_ARN` | no | Future KMS key reference |
| `KMS_REGION` | no | KMS region |

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

## WhatsApp (VW)

| Variable | Required when connected | Description |
|----------|-------------------------|-------------|
| `WHATSAPP_GRAPH_API_VERSION` | yes | e.g. `v21.0` |
| `WHATSAPP_ACCESS_TOKEN` | yes | Resolved via ref in prod |
| `WHATSAPP_APP_SECRET` | yes | Webhook HMAC |
| `WHATSAPP_VERIFY_TOKEN` | yes | Hub verification |

## CRM — Bitrix24 (XY)

| Variable | Required when connected | Description |
|----------|-------------------------|-------------|
| `BITRIX24_CLIENT_ID` | yes | OAuth client id |
| `BITRIX24_CLIENT_SECRET` | yes | OAuth secret |
| `BITRIX24_WEBHOOK_SECRET` | yes | Inbound webhook verification |
| `BITRIX24_BASE_URL` | yes | Tenant portal base URL |

## Email (SMTP)

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `SMTP_HOST` | when email enabled | SMTP server |
| `SMTP_PORT` | no | Default `587` |
| `SMTP_USERNAME` | optional | Auth user |
| `SMTP_PASSWORD` | optional | Auth password |
| `SMTP_FROM` | yes | From address |
| `SMTP_TLS` | no | `true` default |

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
