# ADR-0003: Observer mode first

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

Design partners already use bots, managers, phone numbers, messaging accounts, and CRMs. Replacing those systems before proving measurable value would increase onboarding and operational risk.

## Decision

The first paid release observes the existing workflow. It ingests authorized data, computes deterministic metrics, creates evidence-backed findings and follow-up tasks, and accepts human review. It does not autonomously send outbound messages or replace the CRM.

## Alternatives considered

- Unified inbox in the first release: deferred until observer-mode value is proven.
- Autonomous follow-up: rejected for the first release because consent, channel policy, content safety, and operational controls are not yet approved.
- Offline chat upload only: rejected as the primary product because it does not provide a reliable operating workflow.

## Consequences

- The initial product must coexist with existing channel and CRM operations.
- Suggestions remain clearly labeled and require human action.
- Unified inbox and sending capabilities require separate tasks and approval.

## Security and privacy impact

Observer mode reduces outbound harm but still processes confidential personal data. All access, retention, redaction, audit, and tenant-isolation controls remain mandatory.

## Migration and rollback/remediation

If an integration degrades, disconnect it without disrupting the customer's existing communication workflow. Any future outbound capability must be introduced behind a separate policy and release gate.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/PRODUCT_SPEC.md`, and `docs/INTEGRATIONS.md`, reviewed 2026-07-10.
