# CloserOS AI

CloserOS AI is a multi-tenant sales-operations platform for messaging-based sales teams.

It connects to official business messaging and CRM APIs, observes bot and manager conversations, identifies evidence-backed process failures, generates follow-up tasks, and gives owners a unified operational view.

## Repository status

CLS-001 provides an executable monorepo foundation. CLS-002 adds local-only
PostgreSQL and Redis containers without connecting them to application code.
CLS-003 adds local CI configuration; remote workflow and branch-protection
verification remains pending. The repository still contains no product
features, provider integrations, external AI calls, schemas, migrations, or
production infrastructure.

Read `AGENTS.md`, accepted ADRs, `TASKS.md`, and `PROJECT_STATUS.md` before
making changes. Work on one task ID at a time.

## Prerequisites

The repository pins:

- Node.js `24.14.1` LTS in `.node-version`;
- pnpm `11.11.0` through Corepack in `package.json`;
- Python `3.13.14` in `.python-version`;
- uv `0.11.28` through `tool.uv.required-version` in `pyproject.toml`.
- Docker Engine `24.0+` and Docker Compose v2 `2.24+` for CLS-002.

Install the exact Node.js version and a recent Corepack, then run
`corepack enable pnpm` once so child tools can resolve the pinned pnpm shim.
Install the exact uv version and ensure `uv` is on `PATH`. uv downloads the
pinned Python runtime when necessary.

From a clean checkout, install both workspaces with frozen lockfiles:

```text
corepack pnpm run setup
```

`pnpm-lock.yaml` and `uv.lock` are the only workspace lockfiles.

## Repository structure

```text
apps/
  web/       Next.js executable scaffold
  api/       thin FastAPI executable
  worker/    thin no-op worker executable
packages/
  backend/   shared Python modular-monolith boundaries
  contracts/ documented placeholder; no generated client
  ui/        minimal shared React package
infra/
  docker/    local-only PostgreSQL and Redis Compose environment
docs/
  adr/       accepted architecture decisions
tests/       Python scaffold tests
```

The shared backend package contains the `domain`, `application`,
`infrastructure`, and `interfaces` boundaries. They intentionally contain no
business logic in CLS-001.

## Root commands

Run commands through the root `package.json` interface:

- `corepack pnpm run setup` — frozen pnpm and uv installation;
- `corepack pnpm run format` — Prettier and Ruff formatting;
- `corepack pnpm run format:check` — non-mutating formatting check;
- `corepack pnpm run lint` — ESLint and Ruff;
- `corepack pnpm run typecheck` — strict TypeScript and mypy checks;
- `corepack pnpm run test` — Vitest and pytest;
- `corepack pnpm run build` — production Next.js build;
- `corepack pnpm run quality` — complete local quality gate;
- `corepack pnpm run infra:config` — validate effective Compose configuration;
- `corepack pnpm run infra:up` — start PostgreSQL and Redis and wait for health;
- `corepack pnpm run infra:status` — display service status;
- `corepack pnpm run infra:logs` — follow infrastructure logs;
- `corepack pnpm run infra:check` — verify health and authenticated access;
- `corepack pnpm run infra:down` — stop services and preserve volumes;
- `corepack pnpm run infra:reset` — destructively remove local data volumes;
- `corepack pnpm run infra:clean-checkout` — run isolated reproducibility checks;
- `corepack pnpm run dev:web` — Next.js development server on
  `http://localhost:3000`;
- `corepack pnpm run dev:api` — FastAPI development server on
  `http://localhost:8000` (match the frontend hostname family for browser auth);
- `corepack pnpm run dev:worker` — safe no-op worker execution.

The API exposes `GET /health`, authentication routes at `/api/v1/auth/*`, and
database readiness at `/ready`. The web app calls the API directly from the
browser with cookie credentials. See `docs/AUTHENTICATION_API.md` and
`docs/AUTHENTICATION_FRONTEND.md`.

For local browser authentication testing:

1. copy `.env.example` to `.env` and keep `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`;
2. set `AUTH_ALLOWED_ORIGINS=http://localhost:3000` (avoid mixing `127.0.0.1` and `localhost`);
3. start PostgreSQL, run API migrations separately, then run `dev:api` and `dev:web`.

## Local infrastructure

Docker Compose uses exact official images `postgres:18.4-bookworm` and
`redis:8.8.0-trixie`, project-scoped named volumes, health checks, and
loopback-only default ports:

- PostgreSQL: `127.0.0.1:5432`;
- Redis: `127.0.0.1:6379`.

No `.env` is required for a clean local start. The Compose fallbacks are public,
obviously local-only credentials and are forbidden outside local development.
Copy `.env.example` to the ignored `.env` file to override credentials or host
ports. Run `corepack pnpm run infra:up`, then
`corepack pnpm run infra:check`.

See `infra/docker/README.md` for port troubleshooting, credential handling,
health recovery, safe shutdown, and destructive reset instructions.

## Continuous integration

GitHub Actions runs the existing aggregate quality gate, blocking secret
scanning, and pull-request dependency review. CI uses frozen lockfiles, exact
repository runtime pins, package-manager download caches, read-only repository
permissions, and immutable action SHAs. It supplies no provider credentials and
starts no PostgreSQL or Redis services.

Repository administrators must enable the GitHub dependency graph and require
`Quality / quality`, `Security / secret-scan`, and
`Security / dependency-review` on the default branch. See `docs/CI.md` for
workflow behavior, action pins, rerun instructions, and remote activation
steps.

## Direct dependency purposes

Python runtime dependencies are FastAPI for the HTTP scaffold and Uvicorn for
its local executable server. HTTPX supports API tests. Ruff formats and lints,
mypy performs strict static checking, pytest runs tests, and Hatchling builds
the three workspace packages.

TypeScript runtime dependencies are Next.js, React, and React DOM. ESLint with
the Next.js configuration lints code, Prettier formats it, TypeScript performs
strict checking, Vitest runs scaffold tests, and the `@types` packages provide
library/runtime declarations.

pnpm allows only the reviewed install scripts for the exact transitive
`sharp@0.34.5` and `unrs-resolver@1.12.2` packages. Unlisted dependency build
scripts fail closed.

## Security

Never put secrets in the repository. `.env` and local environment variants are
ignored; `.env.example` contains names and safe defaults only. Tests use no
customer data or paid/external services. Logs and scaffold responses contain no
message content, tokens, or personal data. Never load production data or
customer exports into the local Docker volumes. PostgreSQL is the system of
record; Redis is not a source of truth.

## Product principles

- Observer mode before replacement.
- Official APIs only.
- Evidence before AI claims.
- CRM outcomes before revenue claims.
- Human approval before outbound automation.
- Local redaction before external LLM calls.
- Modular monolith before microservices.
- Production quality is demonstrated by tests and controls, not by the amount of code.
