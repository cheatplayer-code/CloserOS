# ADR-0008: uv and pnpm monorepo tooling

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

The repository will contain Python backend packages and TypeScript web/UI packages. It needs reproducible dependency resolution and cross-platform root commands without adding a heavyweight monorepo orchestrator.

## Decision

Use `uv` as the Python package and workspace manager. Use `pnpm` through Corepack for JavaScript workspaces. Root pnpm scripts invoke pnpm workspace commands and uv commands.

Host Git and CI on GitHub and GitHub Actions. Do not add Nx, Turborepo, Bazel, or Make unless measured build or orchestration requirements justify a later ADR.

The shared Python modular-monolith package is `packages/backend`. Exact supported Python, Node, uv, pnpm, framework, and tool versions are pinned during CLS-001 and committed with one Python workspace lockfile and one pnpm workspace lockfile.

## Alternatives considered

- Poetry or pip-tools: not selected because uv will manage the Python workspace and lock.
- npm or Yarn: not selected because pnpm workspace behavior and storage efficiency fit the repository.
- Nx/Turborepo/Bazel: deferred because current task orchestration is small.
- Make: rejected as a root requirement because the development environment includes Windows.

## Consequences

- Contributors need Corepack and the pinned uv/runtime versions.
- CI uses frozen lockfile installs.
- Root scripts are the documented task interface.

## Security and privacy impact

Committed lockfiles and CI dependency/secret scanning improve supply-chain review. Registry credentials and CI secrets must not be stored in repository configuration or logs.

## Migration and rollback/remediation

Tool replacement requires a later ADR, regenerated lockfiles, clean-checkout verification, and CI rollback instructions. A failed tooling upgrade is reverted by restoring the prior pins and lockfiles without rewriting shared history.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `TASKS.md`, and `docs/DEVELOPMENT_WORKFLOW.md`, reviewed 2026-07-10.
- Exact runtime and tool versions have not yet been selected or externally verified.
