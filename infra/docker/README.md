# Local Docker infrastructure

CLS-002 provides PostgreSQL and Redis for local development only. This is not
deployment configuration and must never be initialized with production data,
customer exports, or real credentials.

PostgreSQL is the system of record. Redis is not a source of truth.

## Prerequisites

- Docker Engine `24.0` or newer using Linux containers.
- Docker Compose v2 `2.24` or newer through `docker compose`.
- The repository prerequisites documented in the root `README.md`.
- Corepack's pinned pnpm shim enabled once with `corepack enable pnpm`.

Docker Desktop is suitable on Windows and macOS. Start Docker Desktop before
running infrastructure commands.

## Reviewed images

- `postgres:18.4-bookworm`
- `redis:8.8.0-trixie`

Verification date: 2026-07-10. Source categories: PostgreSQL official release
announcements, Redis Open Source official GA release notes, and Docker Hub
Docker Official Image tag listings. Both tags are exact stable releases; no
preview or floating `latest` tag is used.

## Local credentials and environment

Compose has committed, obvious local-only fallback values, so a clean checkout
starts without a `.env` file. These public values are not secure and are
forbidden in staging or production.

To override them locally:

```text
copy .env.example .env
```

On POSIX systems, use `cp .env.example .env`. The resulting `.env` is ignored by
Git. `.env.example` documents:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- `POSTGRES_HOST_PORT`;
- `REDIS_PASSWORD`, `REDIS_HOST_PORT`;
- reserved future application values `DATABASE_URL` and `REDIS_URL`.

If an overridden password contains URL-reserved characters, percent-encode the
password in the corresponding URL. CLS-002 does not connect application code to
either URL.

## Commands

Run all commands from the repository root:

- `corepack pnpm run infra:config` validates effective Compose configuration
  without printing it.
- `corepack pnpm run infra:up` starts both services and waits up to 120 seconds
  for healthy status.
- `corepack pnpm run infra:status` displays container and health status.
- `corepack pnpm run infra:logs` follows the last 100 infrastructure log lines.
- `corepack pnpm run infra:check` verifies container health, authenticated
  PostgreSQL access and database existence, authenticated Redis `PING`, and
  unauthenticated Redis rejection.
- `corepack pnpm run infra:down` stops containers without deleting data.
- `corepack pnpm run infra:reset` **deletes both local data volumes** after
  stopping the stack.
- `corepack pnpm run infra:clean-checkout` performs the isolated reproducibility
  test and deletes its temporary containers, volumes, network, and files.

## Ports and persistence

Defaults:

- PostgreSQL: `127.0.0.1:5432`;
- Redis: `127.0.0.1:6379`.

Set `POSTGRES_HOST_PORT` or `REDIS_HOST_PORT` in `.env` to override an occupied
port, then rerun `infra:up`. On Windows, `Get-NetTCPConnection -LocalPort 5432`
can identify a listener. On macOS or Linux, use the platform's `lsof` or `ss`
tool. Compose never binds these services to all host interfaces.

Data persists in project-scoped named volumes. Ordinary `infra:down` preserves
them. Only the explicitly destructive `infra:reset` command removes them.

## Health and recovery

PostgreSQL health uses `pg_isready` with the configured user and database.
Redis health performs an authenticated `PING` without printing its password.

If a service is unhealthy:

1. Run `corepack pnpm run infra:status`.
2. Inspect metadata-only service logs with
   `corepack pnpm run infra:logs`.
3. Confirm Docker has enough disk and memory and that host ports are free.
4. Run `corepack pnpm run infra:down`, then `infra:up`.
5. If disposable local data is corrupt, explicitly run
   `corepack pnpm run infra:reset`, then `infra:up`.

Do not paste credentials, customer content, or production records into issue
reports or local infrastructure logs.
