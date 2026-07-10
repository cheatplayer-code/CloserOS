# Integration Strategy

Provider capabilities, permissions, review requirements, and pricing change. Before implementation, verify the current official documentation and record the verification date in an ADR.

## 1. Common adapter contract

Every channel adapter must implement:

- connection authorization;
- connection status;
- webhook verification;
- event parsing;
- event idempotency key;
- canonical normalization;
- message status normalization;
- token refresh or renewal where supported;
- revocation;
- health check;
- reconciliation;
- outbound capability declaration;
- provider-policy checks.

Provider SDK objects must not cross the infrastructure boundary.

## 2. Observer-mode principle

The first integration observes the existing workflow.

It must not require the business to:
- replace its bot;
- change phone number;
- move every manager into CloserOS;
- disable CRM;
- enable autonomous sending.

CloserOS should distinguish customer, bot, manager, and system messages and analyze handoff quality.

## 3. WhatsApp Business Platform

Use only the official WhatsApp Business Platform / Cloud API path available to the customer.

Implementation areas:
- Meta app and business setup;
- test number;
- webhook verification;
- incoming message events;
- delivery/read/failure statuses;
- customer onboarding flow;
- token and permission lifecycle;
- supported history/backfill behavior;
- 24-hour service window;
- template requirements;
- opt-in evidence;
- pricing and rate limits.

Never assume:
- all existing WhatsApp Business App numbers support identical onboarding;
- six months of history is always available;
- media history is available;
- outbound messages are free;
- a successful API response means delivery.

The adapter must expose capability flags based on the actual connection.

## 4. Instagram Messaging

Use the official Instagram messaging platform for eligible professional accounts.

Implementation areas:
- professional account eligibility;
- Meta app configuration;
- authentication;
- page/account relationship where applicable;
- messaging permissions;
- webhooks;
- app review and advanced access;
- reply-window and policy limits;
- rate limits;
- token expiration and revocation.

Native-app draft interception is not a supported product assumption. Pre-send coaching requires the CloserOS inbox.

## 5. Telegram Business

Use official Telegram Bot API / Telegram Business connection capabilities.

Do not use a userbot that logs in as the customer's personal account.

Implementation areas:
- business connection authorization;
- connection ID and rights;
- business message updates;
- edits/deletions;
- identity mapping;
- send rights;
- connection revocation;
- webhook security;
- history limitations.

Backfill may require lawful export/import if the official connection does not expose the required history.

## 6. CRM integrations

CRM is the source of truth for:
- lead/deal ID;
- owner;
- stage;
- qualified status;
- appointment;
- won/lost outcome;
- amount;
- currency;
- reason;
- timestamps.

Every CRM adapter supports:
- OAuth or official token method;
- incremental sync;
- webhook ingestion;
- periodic reconciliation;
- field mapping;
- conflict visibility;
- deletion/revocation.

Do not silently invent mappings. Tenant administrators confirm them.

## 7. CSV import

CSV remains a supported controlled backfill path.

Requirements:
- schema preview;
- explicit column mapping;
- validation;
- tenant confirmation of lawful source;
- upload size limits;
- malware/content-type checks;
- encrypted temporary storage;
- resumable processing;
- error report;
- deletion according to policy.

## 8. Connection state machine

Canonical states:

```text
draft
authorizing
active
degraded
reauthorization_required
revoked
disconnected
```

Meaning and provider mapping:
- `draft`: local connection record exists but no provider authorization is in progress;
- `authorizing`: the customer has started the provider authorization or verification flow;
- `active`: required credentials, permissions, webhook configuration, and health checks satisfy the adapter's verified requirements;
- `degraded`: the connection still provides partial or uncertain service, such as delayed events or a non-critical health failure;
- `reauthorization_required`: credentials are expired/invalid, required permissions are missing, or provider/customer action is required before normal processing can continue;
- `revoked`: the provider or customer has revoked authorization;
- `disconnected`: the tenant explicitly disconnected the integration and CloserOS has stopped processing it.

Each adapter maps its verified provider-specific statuses and error conditions to this canonical state machine. The original provider status and reason remain in adapter metadata. Unknown or ambiguous provider conditions must not map to `active`; they map to `degraded` or `reauthorization_required` according to whether safe partial operation remains possible. The mapping, official source, and verification date must be recorded in the provider ADR and covered by adapter contract tests.

Canonical transition rules are defined in `docs/DOMAIN_MODEL.md`. Provider adapters may restrict transitions based on verified provider behavior but may not introduce provider-specific domain states.

Dashboard must show:
- last event time;
- last successful API call;
- permissions;
- capabilities;
- data freshness;
- action required.

## 9. Idempotency and ordering

Providers may deliver:
- duplicate events;
- delayed events;
- out-of-order events;
- retries after timeout;
- edits and deletes.

Store original messages as immutable records. Store edits, deletes, and delivery-state changes as separate immutable events, then derive the current message projection using verified provider semantics. Never assume webhook arrival order equals message or status order.

## 10. Outbound safety

Before any send:
- human authorization or approved automation rule;
- opt-in;
- allowed time window;
- approved template where required;
- tenant policy;
- rate limit;
- content safety;
- audit record.

The initial production release has no autonomous outbound sending.
