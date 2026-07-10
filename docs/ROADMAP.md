# Production Roadmap

This roadmap targets a real paid production pilot, not a disposable demo.

Dates are estimates, not promises. Provider review, legal work, and customer access can dominate the schedule.

## Phase 0 — Decisions and legal design

Outputs:
- first vertical selected;
- first channel selected;
- first CRM selected;
- paid design partner identified;
- data-flow map;
- counsel review commissioned;
- hosting shortlist;
- success metrics agreed.

Exit gate:
- business will sign and pay for a defined observer-mode pilot;
- data category is acceptable;
- official API path exists.

## Phase 1 — Platform foundation

Build:
- monorepo;
- local infrastructure;
- CI;
- identity;
- tenant isolation;
- roles;
- audit log;
- PostgreSQL schema;
- encrypted data model;
- queue;
- health checks.

Exit gate:
- cross-tenant tests pass;
- backup and migration approach exists;
- no secrets in repository.

## Phase 2 — Conversation and AI foundation

Build:
- canonical contracts;
- ingestion;
- CSV backfill;
- redaction;
- sensitive-content blocking;
- deterministic metrics;
- AI gateway;
- evidence-backed findings;
- human review.

Exit gate:
- evaluation baseline exists;
- no raw PII reaches external AI in tests;
- invalid evidence is rejected.

## Phase 3 — Core product UI

Build:
- dashboard;
- conversation review;
- manager scorecards;
- follow-up queue;
- connection health;
- admin controls.

Exit gate:
- all aggregates drill to evidence;
- no unsupported revenue claims;
- role-based access passes.

## Phase 4 — First official channel

Build:
- provider app;
- authorization;
- webhooks;
- idempotency;
- token lifecycle;
- event normalization;
- status handling;
- reconciliation;
- sandbox tests.

Exit gate:
- provider test account runs reliably;
- duplicate and delayed events are handled;
- connection revocation is safe.

## Phase 5 — First CRM

Build:
- deal/lead sync;
- outcome mapping;
- owner mapping;
- reconciliation;
- data freshness;
- revenue-at-risk ranges.

Exit gate:
- CRM outcome remains authoritative;
- calculations expose assumptions.

## Phase 6 — Production hardening

Build:
- Kazakhstan deployment;
- secrets manager;
- monitoring;
- alerts;
- encrypted backups;
- restore test;
- retention;
- deletion;
- export;
- incident response;
- legal documents;
- support-access controls.

Exit gate:
- `docs/DEFINITION_OF_DONE.md` production gate passes.

## Phase 7 — Paid observer-mode pilot

Operate:
- one tenant;
- one official channel;
- one CRM or controlled outcome import;
- baseline period;
- weekly reviews;
- model quality monitoring;
- customer feedback;
- support runbook.

Exit gate:
- invoice paid;
- customer uses output;
- measurable process improvement or clear evidence of non-value;
- security and reliability acceptable.

## Phase 8 — Unified inbox and live coach

Only after observer-mode value is proven.

Build:
- inbox;
- assignment;
- composer;
- approved outbound;
- AI draft;
- pre-send checks;
- provider-policy enforcement;
- delivery state;
- internal notes.

## Phase 9 — Additional channels

Add one at a time:
- second channel;
- second CRM;
- third channel.

Each requires its own operational and compliance gate.

## Funding reality

Cursor and a low-cost LLM API can reduce development cost. They do not pay for:
- production hosting;
- legal review;
- business verification;
- domains and email;
- monitoring;
- backups;
- messaging fees;
- penetration testing;
- customer support.

The first commercial milestone is a paid design-partner agreement that funds real infrastructure and compliance.
