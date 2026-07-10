# Domain Model

## 1. Core entities

### Tenant
A customer organization.

Key invariants:
- has a legal status and lifecycle state;
- owns all customer data;
- has configured retention and time zone;
- cannot access another tenant's records.

### User
A human identity.

### Membership
Links a user to a tenant and roles.

### Manager
A sales representative profile. It may link to a user, CRM owner, and channel identity.

### ChannelConnection
An authorized connection to WhatsApp, Instagram, Telegram Business, or another provider.

Canonical states:
- draft;
- authorizing;
- active;
- degraded;
- reauthorization_required;
- revoked;
- disconnected.

Canonical transitions:
- `draft -> authorizing` when an authorization attempt starts;
- `authorizing -> active` after required credentials, permissions, and verification succeed;
- `authorizing -> draft` when an incomplete or cancelled attempt is reset;
- `active -> degraded` when the connection still functions partially or health is uncertain;
- `active|degraded -> reauthorization_required` when credentials expire, required permissions are lost, or provider action is required;
- `reauthorization_required -> authorizing` when reauthorization starts;
- `active|degraded|reauthorization_required -> revoked` when the provider or customer revokes authorization;
- any non-revoked state may move to `disconnected` after an explicit tenant disconnect;
- `revoked` and `disconnected` require a new authorization flow before returning to `active`.

Provider-specific states are retained in adapter metadata and mapped to these canonical values. Adapters must not add provider states to the domain enum. Ambiguous provider conditions fail closed to `degraded` or `reauthorization_required`, with an action reason recorded.

### Lead
A tenant-scoped sales prospect. Provider identities map to a lead through controlled identity resolution.

### ConversationThread
A provider-specific conversation scoped to exactly one tenant, one ChannelConnection, and one external conversation identifier. Its source history remains independent even when it is associated with a SalesCase.

### SalesCase
An optional tenant-scoped commercial aggregate that may group multiple ConversationThreads, resolved identities, and CRM deals believed to belong to the same sales journey. Association and identity-resolution provenance must be retained. A SalesCase must not merge, reorder, or overwrite source thread histories.

### Message
An immutable canonical representation of an original provider message. Original content, sender, provider timestamp, and source identity are never overwritten.

### MessageRevisionEvent
An immutable event representing a provider-reported edit. The current visible content is a derived projection; the original Message remains available according to authorization and retention policy.

### MessageDeletionEvent
An immutable event representing a provider-reported deletion. The current projection records deletion without erasing the historical event before the applicable retention or deletion workflow requires it.

### MessageDeliveryStatusEvent
An immutable provider delivery-state event. Current delivery state is derived using provider semantics and event ordering; webhook arrival order is not treated as authoritative.

### Deal
A CRM-linked sales opportunity.

CRM remains the authority for final outcome.

### Finding
An evidence-backed issue detected by a deterministic rule, AI, or human reviewer.

### FollowUpTask
A required next action associated with a ConversationThread, SalesCase, or Deal.

### KnowledgeDocument
A tenant-approved source used for grounded recommendations.

### AnalysisRun
A reproducible record of model/provider/prompt/rubric/input hash/output/status.

### AuditEvent
A metadata-only security and compliance record.

## 2. Sender types

Controlled values:

- customer;
- bot;
- manager;
- system;
- unknown.

Do not infer `manager` from message direction alone.

## 3. Commercial lifecycle states

Initial controlled lifecycle:

- new;
- awaiting_business;
- awaiting_customer;
- qualified;
- appointment_proposed;
- appointment_booked;
- won;
- lost;
- closed_unknown.

These states apply to the commercial lifecycle projection of a SalesCase, or to a standalone ConversationThread when no SalesCase exists. CRM states may be mapped to these canonical values while original values remain available.
Won and lost are factual commercial outcomes and may be set only from CRM or explicit authorized human input. AI findings must not set these states.

## 4. Finding taxonomy

Initial examples:

- slow_first_response;
- unanswered_customer_question;
- missing_discovery;
- repeated_bot_question;
- broken_bot_handoff;
- missing_next_step;
- weak_objection_handling;
- overdue_follow_up;
- inaccurate_company_information;
- prohibited_claim;
- cold_or_rude_tone.

Every finding requires:
- taxonomy code;
- severity;
- source: deterministic, AI, human;
- confidence where applicable;
- evidence IDs;
- explanation;
- recommended action;
- rubric version;
- review status.

## 5. Finding review state

- pending;
- accepted;
- rejected;
- corrected;
- not_reviewable.

Corrections are stored as new review records. Do not overwrite the original generated output.

## 6. Score model

### Process metrics
Derived from behavior and rubric.

### Outcome metrics
Derived from CRM facts.

### Confidence
Depends on:
- sample size;
- data completeness;
- connection freshness;
- model confidence;
- reviewer agreement.

No score is valid without its measurement window and sample size.

## 7. Revenue at risk

Entity fields should include:
- basis: revenue, gross profit, or configured value;
- currency;
- stage;
- historical conversion source;
- low/base/high estimates;
- calculation version;
- assumptions;
- confidence;
- time window.

Never store a single unexplained number as factual loss.

## 8. Idempotency

Recommended uniqueness:
- `(tenant_id, provider, external_event_id)`;
- `(tenant_id, channel_connection_id, external_message_id)`;
- `(tenant_id, crm_connection_id, external_deal_id)`.

Provider identifiers must be scoped correctly.

## 9. Retention states

Records must support:
- active;
- scheduled_for_deletion;
- deleted;
- legal_hold where lawfully applicable.

Deletion must account for:
- database rows;
- raw encrypted objects;
- derived content;
- search indexes;
- caches;
- backups according to policy.
