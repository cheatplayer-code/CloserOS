# ADR-0007: ConversationThread and SalesCase

Status: accepted
Date: 2026-07-10
Decision owners: CloserOS owners

## Context

Provider conversations have provider-specific identifiers, ordering, edits, deletes, and retention behavior. A commercial journey may nevertheless span multiple channels, identities, and CRM deals. Treating both concepts as one Conversation creates ambiguous history and identity rules.

## Decision

A `ConversationThread` is scoped to one tenant, one ChannelConnection, and one provider-specific external conversation. Its original messages and immutable events retain their own source ordering and provenance.

An optional `SalesCase` may group multiple ConversationThreads, resolved identities, and CRM deals associated with one commercial journey. Grouping records its source and confidence or authorized human decision. It does not merge, reorder, or overwrite thread histories.

## Alternatives considered

- One cross-channel Conversation entity: rejected because provider history and identity semantics become ambiguous.
- No cross-channel aggregate: rejected because owners may need a commercial view spanning channels and CRM.
- Destructive identity merging: rejected because incorrect resolution would corrupt evidence.

## Consequences

- Thread-level metrics remain reproducible from provider events.
- Case-level aggregates must expose their member threads and mapping provenance.
- Identity resolution needs reviewable mapping records and split/remediation behavior.

## Security and privacy impact

All associations are tenant-scoped. Cross-tenant identity linking is prohibited. Case grouping can increase privacy impact by combining data and therefore requires least-privilege access and auditability.

## Migration and rollback/remediation

Incorrect associations are removed or superseded without modifying source threads. Future schema migrations preserve original identifiers and grouping history.

## Sources verified

- Owner decision recorded 2026-07-10.
- `docs/PRODUCT_SPEC.md`, `docs/DOMAIN_MODEL.md`, and `docs/ARCHITECTURE.md`, reviewed 2026-07-10.
- Provider-specific threading behavior remains subject to official documentation verification.
