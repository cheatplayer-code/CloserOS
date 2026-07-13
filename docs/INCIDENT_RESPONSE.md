# Incident Response

This runbook covers staging and early production incidents for CloserOS Block XY.
It is not a substitute for legal/compliance notification obligations (Block Z).

## Severity levels

| Level | Examples | Response target |
|-------|----------|-----------------|
| S1 | Suspected tenant data leak, active secret exposure | Immediate isolation |
| S2 | API down, worker stopped, migration failure mid-deploy | < 1 hour |
| S3 | Elevated outbox lag, single provider webhook failures | < 4 hours |
| S4 | Non-blocking CI scan finding, doc drift | Next business day |

## First 15 minutes

1. **Assign incident commander** and open a private channel.
2. **Classify severity** using table above.
3. **Preserve evidence** — platform logs and audit queries only; no message bodies.
4. **Stabilize** — scale/restart API or worker; disable compromised credentials.
5. **Communicate** — internal stakeholders; customers only with compliance approval.

## Common playbooks

### Suspected secret leak

1. Rotate affected secrets (`docs/SECRET_MANAGEMENT.md`).
2. Revoke provider tokens (WhatsApp, Bitrix24) at vendor console.
3. Review audit log for anomalous privileged actions.
4. Run TruffleHog on recent commits if leak may be in git.

### Database unavailable

1. Check Supabase status and connection pool saturation.
2. Verify `DATABASE_URL` uses pooler and `sslmode=require`.
3. API `/ready` should return 503 — keep load off until recovery.

### Redis loss

1. Redis is not source of truth — restart Redis service.
2. Run `closeros-worker reconcile-once` after Redis is healthy.
3. Monitor outbox stream length until lag clears.

### Bad deploy / migration

1. Stop worker to prevent partial handler execution on mismatched schema.
2. Check `migrate_status.py` output.
3. Forward-fix migration preferred; restore from backup if data corrupt
   (`docs/BACKUP_RESTORE.md`).

### Webhook abuse

1. Provider signature failures should fail closed (no persistence).
2. Rate-limit at edge if sustained abusive traffic.
3. Never log raw webhook bodies.

## External AI incidents

Set `AI_EXTERNAL_CALLS_ENABLED=false` on API and worker immediately if:

- unexpected external traffic spike;
- vendor breach notification;
- sanitizer false-negative suspicion.

## Post-incident

1. Timeline with correlation IDs (no PII).
2. Root cause and corrective actions.
3. Update `PROJECT_STATUS.md` if product boundaries changed.
4. ADR if architecture or vendor changes.

## Contacts

Define on-call rotation in the team operations doc before paid pilot (Block Z).

## Related documentation

- `docs/OBSERVABILITY.md`
- `docs/SECURITY_COMPLIANCE.md`
- `docs/RETENTION_LEGAL_HOLD.md`
