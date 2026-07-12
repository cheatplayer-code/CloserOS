# WhatsApp Cloud integration

Documentation review date: **2026-07-12**
Graph API version: **v21.0**
Sandbox verification: **NOT completed**

## Overview

CloserOS integrates with the official [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
through a provider adapter inside the modular monolith. Provider-specific JSON is
translated to canonical operations at the infrastructure boundary; domain and
application layers remain provider-neutral.

## Connection lifecycle

| Status | Ingestion | Outbound | Credential refs required |
|--------|-----------|----------|--------------------------|
| `draft` | no | no | no |
| `verification_pending` | yes | no | yes |
| `active` | yes | yes | yes |
| `degraded` | yes | no | yes |
| `disabled` | no | no | no |

Administrators create connections via:

`POST /api/v1/tenants/{tenant_id}/integrations/whatsapp`

Responses expose **reference keys only**, never secret values. Webhook callback path:

`/api/v1/webhooks/whatsapp_cloud/{webhook_public_key}`

## Webhook verification

### GET (Meta subscription)

Query parameters: `hub.mode`, `hub.verify_token`, `hub.challenge`.

CloserOS compares `hub.verify_token` to the resolved verify-token secret for the
connection matching `webhook_public_key`. On success, returns `hub.challenge`
as plain text.

### POST (event delivery)

Route: `POST /api/v1/webhooks/whatsapp_cloud/{channel_connection_id}`

Headers:

- `X-Hub-Signature-256: sha256=<hex-digest>`

Verification uses HMAC-SHA256 over the **exact raw body** with the app secret.
Invalid signatures receive generic `403` denial without leaking reason codes.

Accepted events are encrypted, deduplicated by external event id, and enqueued as
`webhook.normalize` jobs (same pipeline as Block JK).

## Normalization (inbound)

| Meta type | Canonical behavior |
|-----------|-------------------|
| `text` | `NormalizedMessageReceived` with UTF-8 body |
| `interactive` | button/list reply title as message text |
| `reaction` | emoji as message text |
| `image` / `audio` / `video` / `document` / `sticker` | placeholder text + quarantined media metadata |
| `statuses` | `NormalizedDeliveryStatusChanged` (`sent`, `delivered`, `read`, `failed`) |
| unknown types | skipped (no operation) |

## Outbound (human-approved)

1. Manager/owner creates draft on a conversation thread.
2. Authorized user approves; message moves to `queued` and enqueues
   `provider.message.send`.
3. Worker handler resolves credentials, evaluates messaging policy, calls Graph
   `/{phone_number_id}/messages`.
4. Success в†’ `provider_accepted` + canonical outbound message row.
5. Transport failure/timeout в†’ `delivery_unknown` (no automatic resend).

Policy version: `whatsapp_messaging_policy_v1` (24-hour customer service window).

## Environment variables

See `.env.example` for local reference keys:

- `WHATSAPP_GRAPH_API_VERSION` (default `v21.0`)
- `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_APP_SECRET` / `WHATSAPP_VERIFY_TOKEN`
  (resolved via connection reference keys in development)

## Testing

- Fabricated payloads: `tests/vw_support.py`
- Adapter unit tests: `tests/test_whatsapp_adapter.py`
- HTTP integration: `tests/test_whatsapp_webhooks_api.py`,
  `tests/test_whatsapp_integrations_api.py`
- Outbound/handler: `tests/test_outbound_messages.py`,
  `tests/test_provider_message_send_handler.py`

No real Meta credentials in CI. Use `httpx.MockTransport` for Graph client tests.

## Not in v1

- Autonomous outbound messaging
- Media download and malware scanning pipeline
- WhatsApp Business App coexistence guarantees
- Historical backfill beyond webhook + lawful import paths
