# ADR-0002: Provider-neutral AI gateway

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

AI providers, models, costs, availability, and contractual terms can change. Domain rules must not depend on provider SDKs or model-specific response types.

## Decision

Application code depends on an internal AI port for analysis, suggestions, health, and cost estimation. Provider SDKs and payloads remain in infrastructure adapters. Every response is converted to a strict internal schema and validated before use.

DeepSeek may be evaluated as the initial low-cost adapter, but it is not a permanent dependency and cannot process customer data before vendor, legal, location, and security approval.

## Alternatives considered

- Direct provider SDK use in domain/application modules: rejected because it creates vendor coupling.
- No abstraction until a second provider exists: rejected because privacy policy, validation, outage handling, and audit metadata require a stable boundary now.
- Self-hosted model as an immediate requirement: deferred because hosting, quality, and cost evidence do not yet exist.

## Consequences

- Provider capabilities are represented through internal contracts.
- Model changes require evaluation regression.
- Timeouts, retry budgets, circuit breakers, cost controls, and validation are enforced at the gateway.

## Security and privacy impact

The gateway is the mandatory policy and egress boundary. It accepts only policy-approved sanitized input and must not log prompts containing customer text.

## Migration and rollback/remediation

Disable an adapter through configuration and leave analysis pending if it fails security, quality, cost, or availability requirements. Add or replace adapters without changing domain contracts.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/AI_SYSTEM.md`, and `docs/SECURITY_COMPLIANCE.md`, reviewed 2026-07-10.
- No current DeepSeek behavior, pricing, or data terms were verified for this ADR.
