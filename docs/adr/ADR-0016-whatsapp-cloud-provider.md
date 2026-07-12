# ADR-0016: WhatsApp Cloud as first official messaging provider

Status: Accepted
Date: 2026-07-12
Documentation review date: 2026-07-12
Graph API version: v21.0
Sandbox verification: **NOT completed**

## Context

Block VW must deliver the first official messaging provider for CloserOS AI while
preserving:

- tenant isolation and fail-closed webhook verification;
- encrypted storage of provider payloads and outbound drafts;
- human-approved outbound only (no autonomous sending);
- provider-neutral domain boundaries established in Blocks JK and RSTU;
- observer-mode onboarding for design partners.

Meta WhatsApp Cloud API is the selected first channel based on design-partner
demand and official API availability.

## Decision

### Provider kind and adapter boundary

- Introduce `ProviderKind.WHATSAPP_CLOUD` distinct from legacy `whatsapp` enum value.
- Implement `WhatsAppCloudWebhookAdapter` in infrastructure only; normalize to
  existing canonical operations at the boundary.
- Webhook POST route remains generic: `/api/v1/webhooks/{provider}/{connection_id}`.
- Meta GET subscription verification uses dedicated route:
  `/api/v1/webhooks/whatsapp_cloud/{webhook_public_key}`.

### Credential handling

- Persist **reference keys only** (`access_token_ref`, `app_secret_ref`,
  `verify_token_ref`); resolve secrets through `WhatsAppCredentialResolver`.
- Local development uses `EnvWhatsAppCredentialResolver`; production requires
  an approved secrets manager adapter (future XY/Z hardening).
- Never log secret values; `SecretBytes` hides payload from repr.

### Inbound capabilities (v1)

- Text, interactive replies, reactions, delivery/read/failed statuses.
- Media references ingested with placeholder text and quarantined metadata
  (`media_reference=quarantined_pending_scan`); binary download deferred until
  scanner/KMS adapters exist.
- Unknown message types are skipped safely; malformed required fields fail closed.

### Outbound policy

- Draft в†’ human approve в†’ queue в†’ `provider.message.send` outbox handler.
- `WhatsAppMessagingPolicy` v1 enforces Meta 24-hour customer service window:
  free-form text inside window; approved templates outside window.
- No blind resend when status is `provider_accepted`, `delivery_unknown`,
  `delivered`, or `read`.
- Provider transport errors/timeouts mark `delivery_unknown`, not silent resend.

### Persistence

- Migration `b3d7f1a4c8e6`: `whatsapp_cloud_connections`,
  `provider_message_templates`, `provider_media_references`, `outbound_messages`,
  `outbound_delivery_attempts`.
- Outbox kinds: `provider.message.send`, `provider.templates.sync`.

### Verification scope

- Automated tests use fabricated payloads, `InjectedWhatsAppCredentialResolver`,
  and `httpx.MockTransport`; no real Meta credentials in CI.
- Live sandbox verification is documented in `docs/WHATSAPP_SANDBOX_VERIFICATION.md`
  and remains **pending** as of 2026-07-12.

## Consequences

- Instagram and Telegram remain deferred until after XY/Z priorities.
- Media download, malware scanning, and template sync scheduling require follow-up
  hardening tasks.
- Design-partner pilot follows `docs/DESIGN_PARTNER_PILOT.md` with observer mode
  default.

## Related documents

- `docs/WHATSAPP_CLOUD.md`
- `docs/PROVIDER_CAPABILITY_MATRIX.md`
- `docs/WHATSAPP_SANDBOX_VERIFICATION.md`
- ADR-0013 (ingestion pipeline)
- ADR-0003 (observer mode first)
