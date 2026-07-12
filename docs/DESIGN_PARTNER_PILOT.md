# Design partner pilot вЂ” WhatsApp Cloud

Documentation review date: **2026-07-12**
Initial channel: **WhatsApp Cloud API (official)**
Sandbox verification: **NOT completed**

## Purpose

Onboard the first paid design partner in **observer mode** using the official
WhatsApp Business Platform path. CloserOS ingests conversations, computes metrics,
runs governed AI analysis, and surfaces follow-up tasks вЂ” without autonomous
outbound messaging.

## Pilot scope (v1)

### In scope

- One tenant, one WhatsApp Cloud connection, one WABA phone number
- Inbound text, interactive replies, reactions, delivery statuses
- Media references quarantined pending future scanner adapter
- Owner/sales-head dashboard and conversation review (sanitized text)
- Human-approved outbound replies (optional, policy-gated)
- Audit trail for connection, webhook, draft, approve, and send events

### Out of scope

- Autonomous follow-up sends
- Instagram, Telegram, or CRM sync (Block XY)
- Production Kazakhstan hosting sign-off (Block Z)
- Full media download and malware scanning pipeline

## Onboarding sequence

1. **Legal / DPA** вЂ” design-partner agreement and data-processing terms signed.
2. **Meta app setup** вЂ” partner-owned or CloserOS-assisted Meta business app;
   record app ID, WABA ID, phone number ID.
3. **CloserOS connection** вЂ” OWNER/COMPLIANCE_ADMIN creates WhatsApp integration
   with credential reference keys (secrets in approved store).
4. **Webhook subscription** вЂ” configure Meta callback URL; run GET verification.
5. **Sandbox verification** вЂ” complete `docs/WHATSAPP_SANDBOX_VERIFICATION.md`.
6. **Observer period** вЂ” minimum 2 weeks ingest before outbound enablement review.
7. **Outbound opt-in** вЂ” explicit partner approval; train managers on approve flow.

## Roles

| Action | OWNER | SALES_HEAD | COMPLIANCE_ADMIN | MANAGER |
|--------|-------|------------|------------------|---------|
| View integrations | yes | yes | yes | no |
| Create/update connection | yes | no | yes | no |
| Verify/disable connection | yes | no | yes | no |
| Create outbound draft | yes | yes | no | scoped |
| Approve outbound send | yes | yes | no | scoped |

## Success criteria

- Webhook acceptance p99 < 2s (ack only; normalize async)
- Zero cross-tenant data incidents
- AI findings include evidence message IDs on sampled review
- Partner confirms metrics match manual spot checks
- No secret or message body in application logs (spot audit)

## Rollback

- Disable connection via API (`/disable`) вЂ” stops outbound and rejects new webhook processing for inactive statuses
- Revoke Meta app tokens at provider
- Retain encrypted data per tenant retention policy

## Open items before production pilot

- [ ] Execute sandbox verification checklist
- [ ] Remotely verified CI on `feat/vw-whatsapp-provider`
- [ ] Counsel review of Kazakhstan data location for Meta subprocessors
- [ ] Production secrets manager adapter for WhatsApp credentials
