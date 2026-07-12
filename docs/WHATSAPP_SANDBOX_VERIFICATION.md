# WhatsApp Cloud sandbox verification checklist

Documentation review date: **2026-07-12**
Graph API version: **v21.0**
Status: **NOT completed**

This checklist records manual verification against Meta's official WhatsApp Cloud
API documentation. Automated CI tests use fabricated payloads only; they do **not**
substitute for sandbox verification.

## Prerequisites

- [ ] Meta developer app with WhatsApp product enabled
- [ ] Test WABA and test phone number assigned
- [ ] App ID, phone number ID, and WABA ID recorded in secure storage (not repo)
- [ ] CloserOS tenant connection created with reference keys pointing to secrets manager
- [ ] Public HTTPS webhook URL reachable from Meta (tunnel or staging)

## GET webhook verification

- [ ] Configure callback URL:
  `https://<host>/api/v1/webhooks/whatsapp_cloud/<webhook_public_key>`
- [ ] Set verify token to match tenant connection `verify_token_ref` secret
- [ ] Meta hub challenge returns `200` with challenge body
- [ ] Wrong verify token returns generic `403`

## POST webhook signature

- [ ] Send test message from Meta test number to business number
- [ ] CloserOS accepts POST with valid `X-Hub-Signature-256`
- [ ] Tampered body returns `403`
- [ ] Duplicate delivery is idempotent (single encrypted payload + normalize job)

## Inbound message types

- [ ] Text message appears in conversation thread after normalize worker runs
- [ ] Interactive button reply normalized
- [ ] Delivery status events update delivery projection
- [ ] Media message stored with quarantine placeholder (no raw binary in PostgreSQL)

## Outbound (human-approved)

- [ ] Draft created via API/UI
- [ ] Approve queues `provider.message.send`
- [ ] Free-form reply within 24h window succeeds
- [ ] Free-form outside window blocked by policy
- [ ] Approved template send succeeds outside window
- [ ] Simulated provider timeout marks `delivery_unknown` without resend

## Security checks

- [ ] API responses never include access token or app secret values
- [ ] Application logs contain metadata only (no message bodies, no secrets)
- [ ] Cross-tenant webhook connection id denied

## Sign-off

| Field | Value |
|-------|-------|
| Verification date | _pending_ |
| Verified by | _pending_ |
| Meta app ID | _redacted_ |
| Graph API version | v21.0 |
| Notes | Local implementation complete; live sandbox not executed |
