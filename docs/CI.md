# Continuous Integration

CloserOS uses blocking GitHub Actions workflows for quality, security, container
supply chain, and Redis integration tests.

## Quality workflow

`.github/workflows/quality.yml` runs for pull requests targeting `master`,
pushes to `master`, and manual dispatches. Stable branch-protection check names:

- `Quality / quality`
- `Quality / redis-integration`

### `quality` job

The Ubuntu job:

1. checks out the repository without persisting credentials;
2. installs Node.js `24.14.1` and Python `3.12.13` from repository version files;
3. enables pnpm `11.11.0` through Corepack and installs uv `0.11.28`;
4. restores package-manager download caches;
5. runs `corepack pnpm install --frozen-lockfile`;
6. runs `uv sync --all-packages --frozen`;
7. runs `corepack pnpm run quality` with PostgreSQL and Redis service containers.

Service containers supply `TEST_DATABASE_URL` and `TEST_REDIS_URL` for integration
tests embedded in the aggregate gate.

### `redis-integration` job

Dedicated job running:

```bash
uv run pytest -m redis_integration -ra
```

against a Redis `8.8.0-trixie` service container. Fails if stream queue regressions
slip past the broader gate.

`AI_EXTERNAL_CALLS_ENABLED` is explicitly `false`. No provider key or repository
secret is supplied for default test runs.

## Containers workflow

`.github/workflows/containers.yml` (Block XY) builds `api`, `worker`, and `web`
images on `ubuntu-24.04` using `infra/docker/Dockerfile.*` and the Docker CLI
already present on the runner. No Docker Action wrappers are used.

For each image:

1. `docker buildx build --load` (no registry push on ordinary CI);
2. SPDX SBOM generation via pinned standalone `syft` (`scripts/ci/security-tools.lock`);
3. Grype vulnerability scan — fails on fixable `HIGH` and `CRITICAL` findings
   (`--only-fixed`, equivalent to the prior `ignore-unfixed: true` policy);
4. SBOM and vulnerability JSON uploaded as a single workflow artifact.

The `publish-on-tag` job pushes immutable tags to `ghcr.io` **only** when the ref
matches `v*`. It does not publish `latest`.

Stable branch-protection check name: `Containers / build-and-scan`.

## Security workflow

`.github/workflows/security.yml` runs secret scanning for pull requests
targeting `master`, pushes to `master`, and manual dispatches. Dependency review
runs only for pull requests, where a base-to-head dependency change exists.

Stable branch-protection check names are:

- `Security / secret-scan`;
- `Security / dependency-review`.

TruffleHog scans the checked-out repository and complete available Git history.
It fails on `unverified` or `unknown` secret findings. Verification is disabled
so the scanner does not send candidate credentials to provider APIs. No broad
exclusion or allowlist is configured.

GitHub Dependency Review evaluates dependency changes exposed by the repository
dependency graph, including committed `pnpm-lock.yaml` and `uv.lock` data. It
fails when a newly introduced dependency has a `high` or `critical` known
vulnerability. The dependency graph must recognize both ecosystems before this
check is treated as operational.

## Workflow security

Both workflows declare only `contents: read`. Checkout credentials are not
persisted. They do not use `pull_request_target`, write permissions,
`continue-on-error`, deployment commands, package publication, production
credentials, or automatic commits. Superseded runs are cancelled and every job
has a timeout.

Every action reference is an immutable full commit SHA with its reviewed
release tag in a comment:

- `actions/checkout` at
  `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` (`v7.0.0`);
- `actions/setup-node` at
  `48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e` (`v6.4.0`);
- `actions/cache` at
  `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` (`v6.1.0`);
- `actions/setup-python` at
  `ece7cb06caefa5fff74198d8649806c4678c61a1` (`v6.3.0`);
- `astral-sh/setup-uv` at
  `11f9893b081a58869d3b5fccaea48c9e9e46f990` (`v8.3.2`);
- `trufflesecurity/trufflehog` at
  `27b0417c16317ca9a472a9a8092acce143b49c55` (`v3.95.9`);
- `actions/dependency-review-action` at
  `a1d282b36b6f3519aa1f3fc636f609c47dddb294` (`v5.0.0`);
- `actions/upload-artifact` at
  `ea165f8d65b6e75b540449e92b4886f43607fa02` (`v4.6.2`).

Container security tools are pinned in `scripts/ci/security-tools.lock` and
installed by `scripts/ci/install_security_tools.sh` with committed SHA-256
verification before extraction. External action pins are also recorded in
`.github/action-pins.json` and validated offline by
`scripts/ci/validate_action_pins.py`.

Action upgrades require reviewing the official release, resolving its tag to a
commit through the official GitHub repository, updating the SHA and tag comment
together, and rerunning both workflows.

## Remote activation

A repository administrator must complete these GitHub settings after pushing:

1. In **Settings → Security & analysis** (or the equivalent repository security
   settings), enable the dependency graph and confirm it reports dependencies
   from both `pnpm-lock.yaml` and `uv.lock`.
2. Open a pull request targeting `master` and allow both workflows to run.
   Confirm all three stable check names appear and pass. A failed run can be
   rerun from **Actions**, by opening the run and selecting **Re-run failed
   jobs** after the cause is corrected.
3. In the branch ruleset or branch-protection rule for `master`, require a pull
   request and require `Quality / quality`, `Quality / redis-integration`,
   `Containers / build-and-scan`, `Security / secret-scan`, and
   `Security / dependency-review` before merge.
4. Verify with a real pull request that a failing required check blocks merge
   and a corrected rerun permits it.

Quality failures, secret findings, dependency-review failures, installation
failures, and workflow execution failures must block merging. Creating workflow
files alone does not enforce this policy.

Remote workflow execution, dependency-graph ingestion, repository plan
eligibility for Dependency Review, and branch-protection enforcement cannot be
verified locally. If GitHub does not ingest either lockfile ecosystem, the
dependency-review requirement remains incomplete and must not be reported as
passed.
