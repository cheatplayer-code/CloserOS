# Staging — Vercel (Next.js Web)

Vercel hosts the `@closeros/web` Next.js application for staging.

Project configuration reference: `infra/vercel/vercel.json`.

## Repository settings

| Setting | Value |
|---------|-------|
| Framework | Next.js |
| Root directory | repository root (monorepo) |
| Install | `corepack enable pnpm && corepack pnpm install --frozen-lockfile` |
| Build | `corepack pnpm --filter @closeros/web build` |
| Output | `apps/web/.next` |

Alternatively import `infra/vercel/vercel.json` into the Vercel project.

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | HTTPS URL of Railway API (baked at build time) |
| `NODE_VERSION` | `24.14.1` (match `.node-version`) |

`NEXT_PUBLIC_*` values are embedded in the client bundle. Use staging-specific
API hostnames only.

## Security headers

`apps/web/next.config.ts` and `infra/vercel/vercel.json` both set baseline
security headers. Vercel edge configuration may add CSP when approved in Block Z.

## Authentication

- Browser calls Railway API with credentialed requests (`credentials: include`).
- `AUTH_ALLOWED_ORIGINS` on the API must include the exact Vercel staging URL.
- CSRF tokens are required on mutating API calls.

## Preview deployments

Preview URLs must be added to `AUTH_ALLOWED_ORIGINS` temporarily or routed through
a fixed staging hostname. Do not point previews at production databases.

## Build vs runtime

The Docker web image (`infra/docker/Dockerfile.web`) mirrors the Vercel build for
CI parity. Production pilot may choose Vercel (web) + Railway (API/worker) as
documented in ADR-0017.
