# Project Status

## Current phase

`P0 — Repository foundation`

## Completed tasks

- `CLS-001 — Initialize monorepo` (2026-07-10)
- `CLS-002 — Local development environment` (2026-07-10)

## Tasks implemented locally; remote verification pending

- `CLS-003 — CI quality gate` (2026-07-10)

## Last updated

2026-07-10

## What exists

- Product specification
- Architecture specification
- Domain model
- Security and compliance requirements
- Messaging and CRM integration strategy
- AI system specification
- Production roadmap
- Cursor project rules
- Accepted architecture decision records under `docs/adr/`
- Git repository and reproducible pnpm/uv workspaces
- Executable Next.js, FastAPI, and no-op worker scaffolds
- Shared Python backend boundaries under `packages/backend`
- Shared TypeScript UI package and documented contracts placeholder
- Root formatting, linting, type-checking, test, build, and development commands
- Python and TypeScript scaffold tests
- Local-only PostgreSQL and Redis Docker Compose environment
- Effective Compose configuration validation and live authenticated health checks
- Isolated clean-checkout verification with project-scoped cleanup
- GitHub Actions quality, secret-scanning, and dependency-review workflows
- Focused CI operations and branch-protection documentation

## What does not exist yet

- Product feature or business-domain code
- Database schema
- Remotely verified CI execution and branch-protection enforcement
- Deployment environment
- Executed legal review
- Provider test applications
- Paid design partner

## Current decisions

- Product working name: CloserOS AI
- Architecture: modular monolith
- Shared Python backend package: `packages/backend`
- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Python workspace and package manager: `uv`
- JavaScript package manager: `pnpm` through Corepack
- Root task execution: root pnpm scripts invoking pnpm workspace and uv commands
- Git hosting and CI: GitHub and GitHub Actions
- Backend contract direction: Pydantic models exposed through OpenAPI; TypeScript client generation deferred to a later ADR and task
- Database: PostgreSQL
- Queue/cache: Redis, which is not a source of truth
- Reliable asynchronous processing: transactional outbox backed by PostgreSQL
- Conversation model: one provider-specific `ConversationThread`; optional `SalesCase` groups related threads, identities, and CRM deals
- External AI: provider-neutral gateway, DeepSeek as initial low-cost provider
- External AI data policy: sanitized text only; sanitized text remains potentially pseudonymized personal data until qualified counsel approves otherwise
- Commercial outcome authority: CRM or explicit authorized human input, never AI inference
- Initial outbound policy: no autonomous sending
- Initial onboarding mode: observer mode
- Initial channel: not finalized; select using actual design-partner demand
- Initial production hosting: Kazakhstan jurisdiction, provider not finalized
- Pinned runtimes: Python `3.12.13` and Node.js `24.14.1` LTS
- Pinned package managers: uv `0.11.28` and pnpm `11.11.0` through Corepack
- Python quality tools: Ruff `0.15.21`, mypy `2.2.0`, pytest `9.1.1`
- TypeScript quality tools: Prettier `3.9.4`, ESLint `9.39.4`, TypeScript
  `6.0.3`, Vitest `4.1.10`
- Frameworks: FastAPI `0.139.0`, Uvicorn `0.51.0`, Next.js `16.2.10`,
  React `19.2.7`
- ESLint 9 is retained because transitive Next.js lint plugins do not yet
  declare ESLint 10 peer compatibility.
- pnpm dependency build scripts fail closed except reviewed exact transitive
  packages `sharp@0.34.5` and `unrs-resolver@1.12.2`.
- Local PostgreSQL image: `postgres:18.4-bookworm`.
- Local Redis image: `redis:8.8.0-trixie`; Redis remains a delivery/cache
  mechanism and is not a source of truth.
- Local Compose credentials use public, obvious non-production fallbacks.
  Developers may override them in an untracked `.env`; they are forbidden in
  staging and production.
- CI uses GitHub Actions with workflow-level `contents: read`, checkout
  credentials disabled, bounded timeouts, and superseded-run cancellation.
- CI quality uses Node.js `24.14.1`, Python `3.12.13`, pnpm `11.11.0`, and uv
  `0.11.28`; fresh runners install from both frozen lockfiles and cache only
  package-manager downloads.
- CI secret scanning uses TruffleHog `v3.95.9` at
  `27b0417c16317ca9a472a9a8092acce143b49c55`, with provider verification
  disabled and blocking `unverified` and `unknown` findings.
- Pull-request dependency scanning uses GitHub Dependency Review `v5.0.0` at
  `a1d282b36b6f3519aa1f3fc636f609c47dddb294`, blocking `high` and `critical`
  newly introduced vulnerabilities.
- All GitHub Actions are pinned to full reviewed commit SHAs; the complete pin
  inventory is recorded in `docs/CI.md`.

## Open decisions requiring owner input

1. First vertical market.
2. First official messaging channel.
3. First CRM integration.
4. Hosting provider in Kazakhstan.
5. Production authentication provider and session architecture.
6. Production encryption and KMS strategy.
7. Legal counsel and approved data-processing model, including treatment and location of sanitized/pseudonymized text.
8. Pilot price, scope, and design-partner contract.

## Active risks

- The budget is insufficient for ongoing production infrastructure and legal work without pilot revenue.
- Meta app review and business onboarding timelines are outside our control.
- Exact platform permissions and pricing can change.
- External LLM processing is not acceptable for raw or sensitive personal data.
- Sanitized text remains potentially pseudonymized personal data and cannot be treated as anonymous without qualified legal approval.
- The team has not yet established evaluation accuracy on real, lawfully obtained conversations.
- FastAPI's current `TestClient` re-export emits a non-failing deprecation
  warning about the future HTTPX-to-HTTPX2 transition. Scaffold behavior is
  verified, but the test dependency should be reassessed during a future
  framework upgrade.
- Clean dependency installation is network-intensive on Windows and required a
  bounded retry when the npm registry timed out on large Next.js/SWC packages.
- Live Docker verification has run on Windows only; macOS and Linux behavior is
  designed to be portable but has not been executed in this repository.
- CLS-003 workflows have not run on GitHub. Dependency-graph recognition of
  both `pnpm-lock.yaml` and `uv.lock`, repository-plan eligibility for
  Dependency Review, stable remote check names, and branch-protection behavior
  remain unverified.

## CLS-001 verification

Completed on Windows with Python `3.12.13`, Node.js `24.14.1`, uv `0.11.28`,
and pnpm `11.11.0`.

- Frozen setup: passed (`corepack pnpm run setup`).
- Formatting: passed (`corepack pnpm run format:check`).
- Linting: passed (`corepack pnpm run lint`).
- Static typing: passed (`corepack pnpm run typecheck`).
- Tests: passed; 1 Vitest test and 3 pytest tests
  (`corepack pnpm run test`).
- Web production build: passed (`corepack pnpm run build`).
- API import and live `GET /health` smoke check: passed.
- Worker root entry point: passed.
- Aggregate quality gate: passed (`corepack pnpm run quality`).

No PostgreSQL, Redis, Docker Compose service, CI workflow, product feature,
provider integration, customer data, or secret was added. No commit was created
because it was not requested.

CLS-001 was independently reverified before CLS-002. Frozen installation,
formatting, linting, Python and TypeScript type checks, tests, web build, and
the aggregate quality gate all passed. No application-level PostgreSQL or Redis
implementation was present. The only correction discovered during
clean-checkout testing was documentation and isolated setup for enabling the
Corepack pnpm shim required by Next.js's native-package fallback.

## CLS-002 verification

Completed on Windows 11 with Docker Engine `29.1.3` and Docker Compose
`v2.40.3-desktop.1`.

- Official stable sources and Docker Official Image listings were verified on
  2026-07-10 for `postgres:18.4-bookworm` and `redis:8.8.0-trixie`; both exact
  manifests resolved successfully.
- Effective configuration validation passed
  (`corepack pnpm run infra:config`).
- PostgreSQL and Redis started and reached Docker `healthy` status
  (`corepack pnpm run infra:up`).
- Authenticated PostgreSQL access succeeded and confirmed the configured
  database exists.
- Authenticated Redis `PING` returned `PONG`; unauthenticated `PING` was
  rejected.
- Existing tests and the complete repository quality gate passed.
- A cache-free clean-checkout simulation copied only repository files to a
  temporary directory, used fresh temporary pnpm/uv caches, allocated isolated
  host ports, used a unique Compose project, completed frozen installation,
  config validation, healthy startup, live authentication checks, and the full
  quality gate.
- The clean-checkout containers, volumes, network, files, and temporary caches
  were removed; the normal local stack remains healthy.
- Security review found no real secret, all host ports are loopback-only,
  authentication is required, images are pinned, and no privileged container,
  Docker socket, host bind mount, or production/customer data was added.

Files added or changed for CLS-002:

- `infra/docker/compose.yaml`
- `infra/docker/validate.mjs`
- `infra/docker/check.mjs`
- `infra/docker/clean-checkout.mjs`
- `infra/docker/README.md`
- `.env.example`
- `package.json`
- `README.md`
- `PROJECT_STATUS.md`

The initial PostgreSQL 18 startup exposed its new required data mount at
`/var/lib/postgresql`; the Compose mount was corrected and only the empty
volumes created by that failed attempt were reset. No schema, migration,
application database client, Redis client, queue, CI workflow, or later-task
feature was added. No commit was created.

## CLS-003 verification

Status: **Implemented locally; remote verification pending**.

Remote verification started on 2026-07-10:

- initial remote commit:
  `52f8a715053728621ed2c9a0e2e2799176d5dbbb`;
- verification branch: `chore/verify-cls-003`;
- `Quality / quality`, `Security / secret-scan`, and
  `Security / dependency-review` results: pending.

Created:

- `.github/workflows/quality.yml`;
- `.github/workflows/security.yml`;
- `docs/CI.md`.

Configured stable checks:

- `Quality / quality`;
- `Security / secret-scan`;
- `Security / dependency-review`.

The quality workflow runs on pull requests targeting `master`, pushes to
`master`, and manual dispatches. One Ubuntu job installs exact repository
runtimes and package managers from frozen lockfiles, restores pnpm and uv
download caches keyed by the relevant lockfiles, sets
`AI_EXTERNAL_CALLS_ENABLED=false`, and runs the existing
`corepack pnpm run quality` command once.

The security workflow runs TruffleHog against repository content and available
Git history on pull requests, pushes to `master`, and manual dispatches.
TruffleHog verification is disabled so candidate secrets are not sent to
provider APIs. Dependency Review runs only on pull requests and blocks newly
introduced `high` or `critical` vulnerabilities. Both workflows use only
`contents: read`, do not persist checkout credentials, and define timeouts and
concurrency cancellation.

Reviewed immutable action pins:

- `actions/checkout` `v7.0.0`:
  `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`;
- `actions/setup-node` `v6.4.0`:
  `48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e`;
- `actions/cache` `v6.1.0`:
  `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`;
- `actions/setup-python` `v6.3.0`:
  `ece7cb06caefa5fff74198d8649806c4678c61a1`;
- `astral-sh/setup-uv` `v8.3.2`:
  `11f9893b081a58869d3b5fccaea48c9e9e46f990`;
- `trufflesecurity/trufflehog` `v3.95.9`:
  `27b0417c16317ca9a472a9a8092acce143b49c55`;
- `actions/dependency-review-action` `v5.0.0`:
  `a1d282b36b6f3519aa1f3fc636f609c47dddb294`.

Local verification:

- targeted Prettier validation for workflow YAML and changed Markdown: passed
  after the expanded check identified and formatted `PROJECT_STATUS.md`;
- `git diff --check`: passed, with the limitation that this repository has no
  initial commit and Git reports all files as untracked;
- aggregate quality gate (`corepack pnpm run quality`): passed;
- ESLint, Ruff, TypeScript, mypy, one Vitest test, three pytest tests, and the
  existing Next.js build all passed;
- static workflow review found no unpinned action, `pull_request_target`,
  `write-all`, `continue-on-error`, repository secret reference, provider key,
  or PostgreSQL/Redis service;
- current tests were inspected and contain no provider or external network
  calls;
- `pnpm-lock.yaml`, `uv.lock`, and package manifests were not edited;
- no local dependency installation, cache clearing, workflow emulation, or
  Docker command was run; the existing CLS-002 infrastructure was untouched;
- no networked local shell command was run. Fourteen small read-only GitHub API
  metadata requests resolved seven official release tags and their commit SHAs.

Local shell commands executed:

- `git status --short --branch; git diff -- .; git diff --cached -- .`;
- `Get-FileHash -Algorithm SHA256 'pnpm-lock.yaml','uv.lock','package.json','pyproject.toml','apps/web/package.json','packages/ui/package.json','packages/contracts/package.json' | Select-Object Path,Hash`;
- `corepack pnpm exec prettier --check ".github/workflows/quality.yml" ".github/workflows/security.yml" "docs/CI.md" "README.md" --ignore-path ".gitignore"`;
- `git diff --check`;
- `corepack pnpm run quality`;
- `Get-FileHash -Algorithm SHA256 'pnpm-lock.yaml','uv.lock','package.json','pyproject.toml','apps/web/package.json','packages/ui/package.json','packages/contracts/package.json' | ForEach-Object { Write-Output ($_.Path + ' ' + $_.Hash) }; git status --short --branch`;
- `corepack pnpm exec prettier --check ".github/workflows/quality.yml" ".github/workflows/security.yml" "docs/CI.md" "README.md" "PROJECT_STATUS.md" --ignore-path ".gitignore"` (initial expanded run failed only for `PROJECT_STATUS.md`);
- `corepack pnpm exec prettier --write "PROJECT_STATUS.md" --ignore-path ".gitignore"`;
- the same expanded Prettier check rerun after formatting;
- final `git diff --check`.

Remote activation still required:

1. Push the repository and enable the GitHub dependency graph.
2. Confirm the dependency graph recognizes both `pnpm-lock.yaml` and `uv.lock`.
3. Open a pull request targeting `master` and verify all three checks execute
   and pass.
4. Configure the `master` ruleset or branch protection to require all three
   checks before merge.
5. Verify a failing check blocks merge and a corrected rerun allows it.

Do not mark CLS-003 completed until those remote checks pass. Detailed remote
steps and rerun instructions are in `docs/CI.md`. No commit was created.

## Next recommended task

Complete remote verification for `CLS-003`. After it passes, proceed to
`CLS-010 — Tenant and user domain`.

## Rule for updates

Every completed task must update:

- completed task IDs;
- decisions made;
- remaining risks;
- test results;
- next recommended task.

Do not delete historical decisions. Supersede them with an ADR.

## CLS-003 remote verification

Status: **Remote verification started**.

Verification branch: `chore/verify-cls-003`.

This branch exists only to trigger and verify:

- `Quality / quality`;
- `Security / secret-scan`;
- `Security / dependency-review`.

No application code, dependencies, lockfiles, or Docker configuration were changed.

## CLS-010 identity domain

Status: **Implemented locally; GitHub Pull Request verification pending**.

Branch: `feat/cls-010-identity-domain`.

Implemented:

- stable `Role`, `TenantStatus`, `UserStatus`, `MembershipStatus`, and
  `InvitationStatus` enums;
- `Tenant` with UUID, normalized name, lifecycle status, configured time zone,
  and `RetentionPolicy`;
- `User` with lifecycle status;
- `Membership` linking one user to one tenant with tenant-scoped roles;
- `Invitation` with normalized email, roles, lifecycle status, and
  timezone-aware expiration;
- immutable `RetentionPolicy` for raw messages, sanitized messages, AI outputs,
  audit logs, backups, and post-contract deletion;
- fail-closed tenant access guard;
- denial for cross-tenant membership;
- denial for mismatched user membership;
- denial for suspended tenants;
- denial for disabled users;
- denial for suspended or removed memberships.

Not implemented in CLS-010:

- persistence;
- SQLAlchemy;
- Alembic migrations;
- repositories;
- authentication;
- API routes;
- audit logging;
- role-specific authorization;
- invitation delivery or acceptance workflows.

Consolidated verification (2026-07-11):

- Ruff: passed;
- mypy: 0 errors in 15 source files;
- pytest: 100 passed.

Notes:

- Tenant legal-status controlled values remain unspecified and were not invented.
- `CLS-003` Quality, secret scanning, and dependency review were remotely
  verified successfully.

Next step: open a Pull Request from `feat/cls-010-identity-domain` into
`master` and verify GitHub CI.

After merge, the next development task is `CLS-011` authentication design, not
implementation, because session architecture and provider choice remain open
decisions.
