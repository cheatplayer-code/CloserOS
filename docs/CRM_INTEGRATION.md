# CRM Integration Overview

CRM systems are the **source of truth** for commercial outcomes (won/lost, amount,
stage, owner). CloserOS observes messaging quality; it does not invent revenue
losses or final deal status.

See ADR-0004 and `docs/INTEGRATIONS.md` section 6.

## First integration: Bitrix24

Block XY targets **Bitrix24** as the first CRM adapter using official REST/OAuth
APIs documented by Bitrix.

Planned capabilities (v1):

| Capability | Direction | Notes |
|------------|-----------|-------|
| Deal/lead linkage | CRM → CloserOS | Maps external IDs to `SalesCase` |
| Stage and owner sync | CRM → CloserOS | Incremental + webhook where available |
| Won/lost outcomes | CRM → CloserOS | Authoritative for dashboards |
| Activity notes | CloserOS → CRM | Human-approved only; no autonomous spam |
| Connection revocation | Both | Tenant admin disconnect + token delete |

### Configuration references

Environment variables (see `.env.example`):

- `BITRIX24_CLIENT_ID`
- `BITRIX24_CLIENT_SECRET`
- `BITRIX24_WEBHOOK_SECRET`
- `BITRIX24_BASE_URL`

Secrets resolve at runtime through the platform secret store (`docs/SECRET_MANAGEMENT.md`).
PostgreSQL stores **reference keys** only, mirroring the WhatsApp credential pattern.

### Field mapping

Tenant administrators confirm mappings during onboarding. CloserOS must not
silently invent CRM field mappings.

### Metrics impact

Until CRM is connected, CRM-dependent metrics display `unavailable`. When sync is
outside freshness policy, metrics display `stale` with last successful sync time.

## Adapter contract

Every CRM adapter implements the common contract in `docs/INTEGRATIONS.md`:

- OAuth or official token method;
- incremental sync;
- webhook ingestion where supported;
- periodic reconciliation;
- field mapping with tenant confirmation;
- conflict visibility;
- deletion/revocation.

## Security

- Verify webhook signatures per vendor documentation.
- Encrypt tokens at rest.
- Tenant-scope every query and webhook idempotency key.
- Audit connect/disconnect and manual outcome overrides.

## Related documentation

- `docs/INTEGRATIONS.md`
- `docs/PROVIDER_CAPABILITY_MATRIX.md` (CRM row)
- `docs/DEPLOYMENT.md`

Bitrix24-specific adapter documentation will live beside the implementation in a
future revision once sandbox verification is recorded.
