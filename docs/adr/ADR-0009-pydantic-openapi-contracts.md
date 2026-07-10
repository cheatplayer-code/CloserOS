# ADR-0009: Pydantic and OpenAPI contract direction

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

The Python backend needs explicit validated request, response, and canonical schemas. The web application will eventually need typed clients, but selecting and maintaining a generation pipeline is a separate cross-language decision.

## Decision

Define initial backend contracts with strict Pydantic v2 models and expose applicable HTTP contracts through generated OpenAPI. Domain entities remain independent of web-framework and provider SDK types.

Do not introduce TypeScript client generation in CLS-001. Its generator, compatibility policy, artifact ownership, and CI checks require a later ADR and task.

## Alternatives considered

- TypeScript-first schemas: rejected because backend validation and domain/application boundaries are Python-first.
- Hand-maintained duplicate Python and TypeScript schemas: rejected because they can drift.
- Immediate generated client pipeline: deferred until endpoint and compatibility requirements exist.
- Provider schemas as canonical contracts: rejected because vendor payloads must remain at adapter boundaries.

## Consequences

- Pydantic schemas are versioned and compatibility-tested.
- OpenAPI is an interface artifact, not the domain model.
- Breaking API changes require explicit versioning and migration planning.

## Security and privacy impact

Strict schemas support field allowlisting and data minimization. OpenAPI output must not expose secret fields, internal encrypted values, or unauthorized raw-content operations.

## Migration and rollback/remediation

Schema evolution is additive where possible. Breaking changes use explicit versions and a compatibility window. A later TypeScript generation decision must define reproducible generation and rollback of generated artifacts.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/ARCHITECTURE.md`, and `TASKS.md`, reviewed 2026-07-10.
- No TypeScript generator has been selected or verified.
