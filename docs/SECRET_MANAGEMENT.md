# Secret Management

CloserOS never commits production secrets. Staging and production values live in
platform secret stores (Railway, Vercel, Supabase dashboard) or an approved
jurisdiction secrets manager.

## Principles

1. **Reference keys in PostgreSQL** — store `*_ref` names, resolve at runtime.
2. **Fail closed** — missing or weak secrets block startup in `APP_ENV=production`.
3. **No logs** — never log tokens, API keys, webhook secrets, or `DATABASE_URL`.
4. **Rotation** — support dual-read during rotation; audit privileged rotations.
5. **Least privilege** — scope OAuth and webhook credentials per tenant connection.

## Secret categories

| Category | Examples | Storage |
|----------|----------|---------|
| Database | `DATABASE_URL` | Supabase + Railway variables |
| Cache/queue | `REDIS_URL`, `REDIS_PASSWORD` | Railway Redis |
| Encryption | `APP_ENCRYPTION_KEY`, KMS refs | Railway + future KMS |
| Auth | `AUTH_CSRF_SECRET`, `AUTH_RATE_LIMIT_SECRET` | Railway API |
| Messaging | `WHATSAPP_*` refs | Railway API/worker |
| CRM | `BITRIX24_*` | Railway API/worker |
| AI | `DEEPSEEK_API_KEY` | Railway worker (disabled default) |
| Email | `SMTP_*` | Railway API |

## Local development

`.env.example` documents variables with blank or obvious non-production defaults.
Copy to untracked `.env` for overrides. Committed example URIs are public and
forbidden in staging/production.

## Production minimums

`ApiSettings.validate_for_runtime()` enforces:

- `AUTH_CSRF_SECRET` and `AUTH_RATE_LIMIT_SECRET` ≥ 32 bytes in production;
- `AUTH_ALLOWED_ORIGINS` must be HTTPS with real hosts.

Workers require explicit `DATABASE_URL` and `REDIS_URL` in production.

## KMS (future hardening)

Block XY documents KMS variables without enabling a vendor adapter:

- `KMS_PROVIDER`
- `KMS_KEY_ARN`
- `KMS_REGION`

Envelope encryption currently uses `APP_ENCRYPTION_KEY` locally. Production KMS
adapter selection is gated by Block Z legal/infra review.

## Rotation runbook

1. Generate new secret in platform store.
2. Update Railway/Vercel variables for API and worker services.
3. Rolling restart API then worker.
4. Revoke old secret at provider.
5. Record audit event for tenant-scoped connection secrets.

## Verification

- TruffleHog runs on every PR (`Security / secret-scan`).
- Operators run local secret scans before pushing.
- Never use `trufflehog:ignore` on real credentials.
