# Staging — Vercel (Next.js Web)

Vercel hosts the `@closeros/web` Next.js application for staging. The complete
activation order and release evidence are in `docs/STAGING_SIGNOFF.md`.

Project configuration reference: `infra/vercel/vercel.json`.

## Repository settings

| Setting | Value |
|---------|-------|
| Framework | Next.js |
| Root directory | repository root (monorepo) |
| Install | `corepack enable pnpm && corepack pnpm install --frozen-lockfile` |
| Build | `corepack pnpm --filter @closeros/web build` |
| Output | `apps/web/.next` |
| Production branch for staging project | `master` |

Import the GitHub repository and use `infra/vercel/vercel.json` as the project
configuration. Keep one stable staging domain for authentication and CSRF origin
matching.

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | Exact HTTPS origin of the Railway API; baked into the client bundle |
| `NODE_VERSION` | `24.14.1` to match `.node-version` |

`NEXT_PUBLIC_*` values are public and embedded in the browser bundle. Only the
staging API hostname belongs there. Do not add any of the following to Vercel:

- `DATABASE_URL`
- `REDIS_URL`
- authentication secrets
- encryption or KMS keys
- `DEEPSEEK_API_KEY`
- SMTP, CRM, or WhatsApp credentials

Vercel environment-variable changes apply only to new deployments, so redeploy
after changing `NEXT_PUBLIC_API_BASE_URL`.

## Security headers

`apps/web/next.config.ts` and `infra/vercel/vercel.json` set baseline security
headers. Do not weaken them for preview convenience. A stricter CSP remains a
separate release-hardening task.

## Authentication and origins

- Browser calls Railway API with `credentials: include`.
- `AUTH_ALLOWED_ORIGINS` on the API must include the exact stable Vercel staging
  origin, with no wildcard.
- `STAGING_WEB_URL` must match that same origin.
- `NEXT_PUBLIC_API_BASE_URL` must exactly match `STAGING_API_URL`.
- CSRF tokens remain required on mutating API calls.
- Cookie behavior must be verified in a real browser after both deployments are
  active.

Run the environment consistency check from a trusted operator shell:

```bash
uv run python scripts/ops/staging_preflight.py --json
```

## Preview deployments

Do not allow arbitrary Vercel preview URLs to use the shared staging database.
Use one of these patterns:

1. a fixed staging hostname and staging branch;
2. a branch-scoped preview variable pointing at an isolated API/database; or
3. no backend access for untrusted previews.

Adding `*.vercel.app` or `*` to `AUTH_ALLOWED_ORIGINS` is forbidden. Vercel
preview variables may be branch-specific; use them only when the matching API and
data environment are isolated.

## Verification

After deployment:

1. open the stable staging web URL;
2. register/login with the fabricated smoke account;
3. verify tenant selection, dashboard, conversations, tasks, and Reply Copilot;
4. confirm browser requests target only the configured Railway API origin;
5. confirm no secrets appear in client JavaScript, page source, or network
   payloads;
6. run synthetic and DeepSeek staging smoke from a trusted operator shell.

## Rollback

Record the active Vercel deployment ID before S2 activation. Rehearse Instant
Rollback or promote the previous known-good deployment, then verify login and
basic navigation against the still-compatible Railway API.

## Build vs runtime

The Docker web image (`infra/docker/Dockerfile.web`) mirrors the Vercel build for
CI parity. Vercel remains a presentation tier only; the API, worker, secrets,
database, and Redis stay outside Vercel.
