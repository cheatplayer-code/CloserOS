# Retention and Legal Hold

CloserOS retains conversation and audit data according to tenant policy, product
defaults, and legal obligations in the approved jurisdiction.

## Default retention classes

| Data class | Default staging posture | Notes |
|------------|-------------------------|-------|
| Raw message content | Encrypted PostgreSQL | Deleted per tenant policy job (Z) |
| Sanitized content | Encrypted PostgreSQL | May have shorter retention |
| Audit events | Append-only | Longer retention; legal hold exempt |
| Webhook payloads | Encrypted, minimal | Provider reconciliation window |
| AI analysis runs | Metadata + findings | Evidence IDs reference messages |
| Backups | Platform + logical dumps | Encrypted, access-controlled |

## Legal hold

When counsel issues a hold:

1. Mark affected tenants/cases in the legal hold registry (Block Z tooling).
2. Suspend automated deletion jobs for held scopes.
3. Document hold scope, custodian, and expiry conditions.
4. Audit every access to held data.

Holds override default retention but do not override encryption or access control.

## Deletion requirements

Destructive operations require:

- explicit tenant admin or compliance role confirmation;
- append-only audit record with actor and scope;
- verification job reporting rows affected (counts only in logs).

## Cross-border

Production data stays in the Kazakhstan-approved hosting path once legal
verification completes. Staging may use vendor regions documented in ADR-0017
until production jurisdiction is finalized.

## Related documentation

- `docs/SECURITY_COMPLIANCE.md`
- `docs/BACKUP_RESTORE.md`
- `docs/INCIDENT_RESPONSE.md`
