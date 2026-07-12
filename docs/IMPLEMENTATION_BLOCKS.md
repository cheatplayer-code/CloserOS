# Implementation Blocks

This file is the **canonical implementation sequence** for CloserOS AI after the
repository foundation and identity/audit baseline. Future prompts must not rename,
reorder, or redefine these blocks without an explicit accepted update to this file
and `PROJECT_STATUS.md`.

## Combined block order

1. **FG** — shared persistence foundation + canonical conversation contracts
2. **HI** — encrypted message storage + transactional outbox/job foundation
3. **JK** — generic ingestion pipeline + controlled CSV import
4. **LM** — PII/restricted-content detector + deterministic metrics engine
5. **NO** — AI provider gateway + evidence-backed conversation analysis
6. **PQ** — knowledge-base ingestion + tenant-isolated retrieval
7. **RS** — owner dashboard + conversation review
8. **TU** — manager scorecards + follow-up task queue
9. **VW** — design-partner/provider decision package + first official messaging provider
10. **XY** — first CRM integration + production hardening
11. **Z** — compliance, security release gate and paid production pilot

## Block FG scope (completed locally)

- Shared SQLAlchemy base, engine/session, unit-of-work, cursor pagination, and
  tenant-scoped repository helpers.
- Persistent tenants, memberships, invitations with normalized roles.
- Authoritative tenant context resolution and tenant listing API.
- Canonical conversation domain v1, versioned cross-language contracts, PostgreSQL
  schema, repositories, immutable message events, and deterministic projection.
- Tenant-scoped audit query HTTP route.
- Migration revision `d4e8f1a2b3c5` chained from audit revision `8e4b1d0f6a23`.

## Block HI scope (next)

- Encrypted raw message content storage (`content_id` resolution).
- Transactional outbox and job-claim foundation in PostgreSQL.
- No provider ingestion orchestration yet.

## Rules

- Each block builds on prior merged work; do not skip ahead without an ADR.
- Do not implement autonomous outbound messaging in any block before explicit
  product authorization and release-gate approval.
- Raw personal data must not be sent to external LLMs in any block.
- PostgreSQL remains the source of truth; Redis is not a source of truth.
