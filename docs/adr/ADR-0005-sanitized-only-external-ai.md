# ADR-0005: Sanitized-only external AI

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

Conversation content can contain personal, confidential, and restricted data. External AI processing creates legal, location, vendor, and leakage risks.

## Decision

External AI receives only locally sanitized, purpose-approved text after direct-identifier detection, restricted-category detection, stable placeholder replacement, and residual-risk checks. Restricted or uncertain content fails closed.

Sanitized text remains potentially pseudonymized personal data until qualified legal counsel confirms otherwise. It is not treated as anonymous merely because direct identifiers were replaced.

## Alternatives considered

- Send raw conversations under provider contractual controls: rejected.
- Optimistic masking without restricted-category blocking: rejected because false negatives remain high impact.
- Disable all AI permanently: rejected as unnecessary if a lawful, tested sanitized processing model is approved.

## Consequences

- The mapping vault remains encrypted and inaccessible to the AI subsystem.
- Tenant policy, legal approval, vendor approval, location, purpose, budget, and detector result all gate external calls.
- Ingestion and deterministic metrics continue when AI is blocked.

## Security and privacy impact

This reduces but does not eliminate re-identification and cross-border processing risk. Egress tests, metadata-only logs, output residual scans, retention controls, and vendor review remain required.

## Migration and rollback/remediation

External AI can be disabled globally or per tenant without losing source messages. If a detector or vendor is found unsafe, affected analysis is invalidated and reprocessed only after an approved remediation.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/AI_SYSTEM.md`, and `docs/SECURITY_COMPLIANCE.md`, reviewed 2026-07-10.
- Legal treatment and permitted processing locations remain subject to qualified Kazakhstan counsel.
