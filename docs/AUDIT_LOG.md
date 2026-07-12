# Audit log

Block E (CLS-012) implements an append-only, tenant-aware audit subsystem for
security-sensitive platform actions.

## Scope

Recorded today:

- user registration, email verification, login/MFA success and failure;
- session revocation and logout-all;
- password reset request/completion and password change;
- tenant access granted/denied (domain actions reserved for future guards);
- privileged audit log views (`audit.log_viewed`).

Not recorded:

- routine `GET /session` polling;
- message/customer content or arbitrary free-form metadata.

## Event model

Each `AuditEvent` contains:

- event UUID;
- scope (`global` or `tenant`);
- nullable tenant UUID (required for tenant scope);
- actor type and nullable actor UUID;
- controlled dotted action name;
- target type and nullable target UUID;
- timezone-aware `occurred_at`;
- server-generated request correlation UUID;
- allowlisted metadata scalars only;
- database-generated `recorded_at`.

## Metadata policy

Only allowlisted keys such as `outcome`, `reason_code`, `assurance_level`,
`session_stage`, `mfa_method`, `status`, `http_method`, `http_status`,
`route_template`, `source`, and `affected_count` are accepted.

Unknown keys, nested objects, lists, and keys containing sensitive fragments
(`password`, `token`, `email`, `message`, etc.) are rejected.

## Persistence

Table: `audit_events` (revision `8e4b1d0f6a23`).

Immutability:

- repositories expose append and query only;
- PostgreSQL trigger `audit_events_no_update` rejects every UPDATE and DELETE.

Retention purge and SIEM/export are future work and must not reuse ordinary mutation
rights on this table.

## Authorization

`TenantAuditQueryService`:

1. calls the existing fail-closed tenant-access guard;
2. requires `owner` or `compliance_admin`;
3. scopes queries to the authorized tenant;
4. records `audit.log_viewed` on successful access;
5. returns one generic denial message for all rejections.

HTTP audit-query routes and UI viewers are deferred until tenant persistence and
browser session composition provide authoritative tenant/membership context.

## Request correlation

Every API request receives a fresh server-side UUID in `X-Request-ID`. Authentication
audit events for a request share the same correlation ID.

## Related documents

- `docs/adr/ADR-0011-immutable-audit-log-subsystem.md`
- `docs/AUTHENTICATION_API.md`
- `docs/SECURITY_COMPLIANCE.md`
