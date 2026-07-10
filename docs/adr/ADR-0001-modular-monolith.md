# ADR-0001: Modular monolith

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

CloserOS requires strong transactional boundaries, tenant isolation, shared domain behavior, and separate API, worker, and scheduler runtime processes. The initial team and operating budget do not justify distributed-service complexity.

## Decision

Use one modular backend codebase in `packages/backend` with thin process entry points in `apps/api` and `apps/worker`. Deploy API, worker, and scheduler as separate runtime processes where necessary, but keep them within one modular monolith and one source repository.

Module boundaries use domain, application, infrastructure, and interfaces layers. Provider adapters remain infrastructure concerns. Do not introduce microservices, Kubernetes, Kafka, or event sourcing without measured need and a later accepted ADR.

## Alternatives considered

- Channel-specific services: rejected because they duplicate infrastructure and weaken transactional consistency.
- Microservices from the start: rejected because operational and consistency costs exceed demonstrated needs.
- Single synchronous process: rejected because webhook acknowledgement and expensive processing require asynchronous workers.

## Consequences

- Cross-module contracts and ownership must remain explicit.
- PostgreSQL can preserve atomic state changes across modules.
- Runtime processes may scale separately without becoming independent services.
- Future extraction requires measured scaling or isolation evidence.

## Security and privacy impact

Fewer network boundaries reduce secret distribution and accidental personal-data propagation. Tenant authorization remains mandatory in application use cases, regardless of process boundary.

## Migration and rollback/remediation

If a module later requires extraction, define data ownership, consistency, failure recovery, and rollback in a separate ADR. Until then, move accidental cross-module dependencies back behind internal ports.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/SECURITY_COMPLIANCE.md`, reviewed 2026-07-10.
- No external provider behavior is relied upon by this decision.
