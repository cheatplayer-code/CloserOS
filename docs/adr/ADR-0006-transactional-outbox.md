# ADR-0006: Transactional outbox

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

A webhook must be acknowledged quickly, but acknowledging after database persistence and before reliable queue publication can lose accepted work. PostgreSQL is the source of truth; Redis is not.

## Decision

Persist the accepted webhook event and a pending outbox job in one PostgreSQL transaction before acknowledgement. Use the same pattern for internal state changes that require reliable asynchronous work.

An outbox publisher claims committed rows with concurrency-safe database semantics and publishes persisted IDs. Queue payloads do not contain raw customer content. Consumers are idempotent because publication may occur more than once. Pending and timed-out rows are reclaimed, and reconciliation detects work that remains unpublished or unprocessed beyond policy.

## Alternatives considered

- Publish directly after committing: rejected because a crash can lose work.
- Publish before committing: rejected because workers can observe nonexistent or rolled-back state.
- Treat Redis as durable truth: rejected by architecture decision.
- Distributed transactions across PostgreSQL and Redis: rejected as unnecessary complexity.

## Consequences

- At-least-once publication and consumption are expected.
- Outbox retention, retry, dead-letter, metrics, and cleanup policies are required.
- Worker jobs reference persisted IDs and reload authorized state.

## Security and privacy impact

Minimizing queue payloads reduces leakage through Redis and diagnostics. Outbox rows remain tenant-scoped and must not copy raw message bodies unnecessarily.

## Migration and rollback/remediation

If publication is disabled or fails, pending rows remain recoverable in PostgreSQL. Schema changes use forward migrations with remediation plans; cleanup must not delete rows before completion and retention conditions are met.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md` and `docs/ARCHITECTURE.md`, reviewed 2026-07-10.
- Queue library and operational timing parameters remain future implementation decisions.
