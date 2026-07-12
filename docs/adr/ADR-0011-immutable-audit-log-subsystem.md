# ADR-0011: Immutable audit log subsystem

Status: accepted
Date: 2026-07-12
Decision owners: platform engineering

## Context

CloserOS must record security-sensitive actions in an append-only, tenant-aware audit
trail (CLS-012). Audit records must survive actor and tenant lifecycle changes,
exclude message bodies and secrets, and support authorized tenant-scoped review.

## Decision

Implement a framework-independent audit domain with a strict metadata allowlist,
application ports for append-only persistence and tenant-scoped queries, PostgreSQL
storage with CHECK constraints and a trigger that rejects UPDATE/DELETE, and
integration with authentication workflows in the same database transaction for
successful state changes.

Failed login and failed MFA events are recorded in a separate audit transaction
after the rolled-back business transaction completes.

Every HTTP request receives a server-generated correlation UUID returned as
`X-Request-ID`. Client-provided request IDs are ignored.

Tenant audit queries require active tenant membership and either `owner` or
`compliance_admin` role. Successful queries append a tenant-scoped
`audit.log_viewed` event.

No HTTP audit-query route is exposed until browser session composition provides
authoritative selected tenant/membership context.

## Alternatives considered

1. **Application-only immutability** — rejected; direct SQL mutation must fail.
2. **Foreign keys to users/tenants** — rejected; audit history must not disappear
   when referenced rows are deleted.
3. **Arbitrary JSON metadata** — rejected; only allowlisted scalar codes are stored.
4. **Client-provided correlation IDs** — rejected; server generates identifiers.

## Consequences

- Security-sensitive authentication workflows now require audit append before commit.
- Audit query authorization is centralized in `TenantAuditQueryService`.
- Future retention purge requires a dedicated mechanism that does not expose ordinary
  mutation rights on `audit_events`.
- Production database role separation for audit readers/writers remains future work.

## Security and privacy impact

- Raw passwords, tokens, cookies, emails, names, phone numbers, IP addresses, and
  message bodies are rejected from audit metadata.
- Audit `repr` and errors avoid exposing sensitive values.
- Cross-tenant reads are denied with one generic message.

## Migration and rollback/remediation

- Revision `8e4b1d0f6a23` creates `audit_events`, indexes, constraints, and the
  immutability trigger.
- Downgrade drops the trigger, function, indexes, and table. Safe only on empty or
  isolated test databases.

## Sources verified

- Internal security/compliance requirements in `docs/SECURITY_COMPLIANCE.md`
  (reviewed 2026-07-12).
- PostgreSQL trigger documentation for `BEFORE UPDATE OR DELETE` (reviewed 2026-07-12).
