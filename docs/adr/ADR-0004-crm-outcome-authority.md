# ADR-0004: CRM outcome authority

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

Conversation text can suggest intent but cannot reliably establish whether a commercial deal was won or lost. Treating AI inference as a factual outcome would corrupt reporting and revenue claims.

## Decision

CRM is authoritative for qualified, stage, won, lost, amount, currency, reason, and related commercial outcomes. Explicit authorized human input may supply an outcome when the configured workflow permits it and the action is audited. AI must never set or infer factual won/lost state.

Before CRM connection, CRM-dependent metrics display as unavailable. When synchronization exceeds the configured freshness policy, they display as stale with the last successful sync time.

## Alternatives considered

- Infer outcomes from conversation text: rejected as unsupported and unauditable.
- Treat unresolved conversations as lost: rejected because it creates false revenue claims.
- Hide all product value until CRM exists: rejected because process metrics remain useful independently.

## Consequences

- Process and outcome metrics remain separate.
- CRM conflicts are surfaced and reconciled, not silently overwritten.
- Revenue-at-risk remains an estimate with assumptions and ranges.

## Security and privacy impact

CRM ingestion is data-minimized and tenant-scoped. Financial and outcome data requires role-based access and audited changes.

## Migration and rollback/remediation

Incorrect mappings are corrected through versioned mapping changes and reconciliation. Historical source values remain available for audit; AI-derived outcomes are never migrated into factual fields.

## Sources verified

- Owner decision recorded 2026-07-10.
- `AGENTS.md`, `docs/PRODUCT_SPEC.md`, `docs/DOMAIN_MODEL.md`, and `docs/INTEGRATIONS.md`, reviewed 2026-07-10.
- Provider-specific CRM behavior remains unverified until a CRM is selected.
