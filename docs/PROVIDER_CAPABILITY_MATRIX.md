# Provider capability matrix

Documentation review date: **2026-07-12**

This matrix compares **implemented or declared** capabilities in CloserOS v1.
It is not a guarantee of every Meta/Telegram account configuration.

| Capability | WhatsApp Cloud (VW) | Synthetic (JK dev/test) | Instagram | Telegram Business | CRM (XY) |
|------------|---------------------|-------------------------|-----------|-------------------|----------|
| Official API only | yes | test double | planned | planned | planned |
| Webhook HMAC verification | yes (`X-Hub-Signature-256`) | yes (custom header) | — | — | — |
| GET hub verification | yes | no | — | — | — |
| Inbound text | yes | yes | — | — | — |
| Interactive reply | yes | no | — | — | — |
| Reactions | yes | no | — | — | — |
| Message status events | yes | partial | — | — | — |
| Media reference (quarantined) | yes | no | — | — | — |
| Media download + scan | no | no | — | — | — |
| Outbound free-form (24h window) | yes (human-approved) | no | — | — | — |
| Outbound approved template | yes (human-approved) | no | — | — | — |
| Autonomous outbound | **no** | **no** | **no** | **no** | — |
| Template sync job kind | declared (`provider.templates.sync`) | no | — | — | — |
| Historical backfill | lawful import only | CSV import | — | — | — |
| Token rotation | manual via connection update | n/a | — | — | — |
| Sandbox verified (2026-07-12) | **no** | n/a | — | — | — |

## WhatsApp Cloud policy notes (Graph API v21.0)

- Customer service window: 24 hours from last customer inbound message.
- Outside window: approved template messages only.
- API `200` with message id ≠ guaranteed delivery; CloserOS tracks
  `provider_accepted` and provider status webhooks separately.
- Media inbound stored as reference + placeholder until scanner pipeline exists.

## Connection capability flags

`WhatsAppCloudConnection.capabilities` stores the supported set for UI and policy
checks. Capabilities must be a non-empty subset of the adapter's supported enum values.
