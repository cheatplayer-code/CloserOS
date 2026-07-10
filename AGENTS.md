# CloserOS AI — Agent Operating Manual

This file is the primary instruction source for every coding agent working in this repository.

## 1. Product mission

CloserOS AI is a multi-tenant B2B SaaS for sales teams that operate in messaging channels.

It connects to official business messaging and CRM APIs, ingests conversations, computes deterministic sales-process metrics, detects evidence-backed risks with AI, creates follow-up tasks, and gives owners and sales managers a unified operational view.

CloserOS is not:
- a generic chatbot;
- a prompt wrapper;
- an autonomous message sender;
- a system that invents revenue losses;
- a replacement for CRM in the first release.

The product enters a business in observer mode, proves value, and later becomes the team's unified inbox and coaching workspace.

## 2. Non-negotiable product truths

1. Never label estimated money as confirmed lost revenue.
   - Use `revenue_at_risk`.
   - Show assumptions and confidence.
   - CRM outcome data is the source of truth for won/lost status.

2. Every AI finding must be auditable.
   - Include `evidence_message_ids`.
   - Include confidence.
   - Include rubric version and prompt version.
   - A human must be able to accept, reject, or correct a finding.

3. No automatic outbound messages in the initial production release.
   - Suggestions and tasks are allowed.
   - Sending requires a human confirmation and channel-policy checks.

4. Raw personal data must never be sent to an external LLM.
   - Redaction happens locally before the LLM call.
   - Sensitive categories must be blocked, not merely masked optimistically.

5. Use only official messaging and CRM APIs.
   - No WhatsApp Web scraping.
   - No Instagram browser automation.
   - No Telegram userbot impersonation.
   - No undocumented endpoints.

6. Build a modular monolith first.
   - Do not introduce microservices, Kubernetes, Kafka, or event sourcing without a written ADR and proven need.

## 3. Source-of-truth document order

When documents conflict, use this order:

1. `AGENTS.md`
2. Accepted ADRs in `docs/DECISIONS.md`
3. `docs/SECURITY_COMPLIANCE.md`
4. `docs/PRODUCT_SPEC.md`
5. `docs/ARCHITECTURE.md`
6. `docs/DOMAIN_MODEL.md`
7. `docs/INTEGRATIONS.md`
8. `docs/AI_SYSTEM.md`
9. `TASKS.md`
10. Existing implementation

Do not silently resolve a material conflict. Record it in `PROJECT_STATUS.md` and ask for a decision.

## 4. Required workflow for every task

Before editing code:

1. Read this file.
2. Read `PROJECT_STATUS.md`.
3. Read the relevant documents under `docs/`.
4. Inspect existing code and tests.
5. Restate the task, constraints, and acceptance criteria.
6. Produce a short implementation plan.
7. Identify security, privacy, migration, and integration risks.

During implementation:

1. Make the smallest coherent change.
2. Preserve tenant isolation.
3. Add or update tests with the code.
4. Use typed interfaces and validated schemas.
5. Handle retries, timeouts, idempotency, and partial failure where relevant.
6. Never log message bodies, tokens, secrets, access tokens, or raw PII.
7. Do not add a dependency unless its purpose is documented.
8. Do not modify unrelated files.

Before declaring completion:

1. Run formatting.
2. Run linting.
3. Run type checks.
4. Run unit tests.
5. Run relevant integration tests.
6. Review migrations for rollback and data safety.
7. Review authorization and tenant boundaries.
8. Update `PROJECT_STATUS.md`.
9. Update documentation when behavior changed.
10. Report exactly what was tested and what remains unverified.

Never say “production ready” unless every applicable item in `docs/DEFINITION_OF_DONE.md` is satisfied.

## 5. Planned architecture

Repository target:

```text
apps/
  web/                 Next.js + TypeScript
  api/                 FastAPI + Python
  worker/              Python background worker
packages/
  contracts/           Versioned API/event schemas
  ui/                  Shared UI components
infra/
  docker/
  migrations/
docs/
tests/
```

Runtime target:

- Web: Next.js, TypeScript, strict mode.
- API: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- Worker: Python worker using the same domain/application packages.
- Database: PostgreSQL.
- Queue/cache: Redis.
- Object storage: S3-compatible storage hosted in the approved jurisdiction.
- Observability: structured metadata-only logs, metrics, traces, error reporting.
- Local development: Docker Compose.
- Deployment: containers on a Kazakhstan-hosted environment after legal verification.

Do not create separate services for each channel. Channel integrations are adapters inside the modular monolith.

## 6. Backend boundaries

Use these logical layers:

```text
domain/
application/
infrastructure/
interfaces/
```

Rules:

- `domain` contains business rules and must not import web frameworks or vendor SDKs.
- `application` contains use cases and ports/interfaces.
- `infrastructure` implements persistence, queues, LLM providers, and channel adapters.
- `interfaces` contains HTTP routes, webhook handlers, CLI, and worker entry points.
- Vendor payloads must be translated into canonical internal models at the boundary.
- Never let Meta, Telegram, CRM, or LLM-specific schemas leak into the domain layer.

## 7. Frontend rules

- Use server-side authorization, not only hidden UI elements.
- Every tenant-scoped request must derive tenant context from the authenticated membership.
- Never store channel access tokens in the browser.
- Do not render raw PII unless the current role is authorized and the action is audited.
- Owner dashboards must link every aggregate to the underlying evidence.
- AI-generated content must be visibly labeled.
- Show confidence and data freshness where decisions depend on them.
- Use accessible semantic components and keyboard navigation.

## 8. Data and multi-tenancy

- Every tenant-owned row must contain `tenant_id`.
- Composite uniqueness and indexes must include `tenant_id` where applicable.
- Authorization checks are mandatory in the application layer.
- PostgreSQL row-level security may be added as defense in depth, not as the only control.
- Cross-tenant joins are prohibited unless they operate only on explicitly anonymized aggregate data.
- Webhook idempotency keys must be unique per tenant and provider.
- External identifiers are never globally unique unless the provider guarantees it.

## 9. Security rules

- Secrets only through environment variables or a secrets manager.
- Never commit `.env`, private keys, production tokens, database dumps, or customer exports.
- Encrypt raw message content and provider tokens at rest.
- Use TLS for all network traffic.
- Verify webhook signatures according to the provider's current official documentation.
- Apply rate limits and replay protection.
- Use least-privilege OAuth scopes.
- Support token rotation and connection revocation.
- Record security-sensitive actions in append-only audit logs.
- Destructive data operations require explicit confirmation and audit entries.

## 10. AI rules

- External providers receive sanitized text only.
- Use a provider-neutral interface.
- Require structured output validated by Pydantic.
- Reject unknown issue codes.
- Reject evidence IDs not present in the analyzed conversation.
- Store model, provider, prompt version, rubric version, token usage, latency, and result hash.
- Cache only sanitized inputs and validated outputs.
- Do not allow the model to determine factual CRM outcomes.
- Do not use AI output as the sole basis for employee discipline.
- Low-confidence or high-impact findings require human review.

## 11. Integration rules

Before implementing or changing an integration:

1. Verify behavior against the provider's official documentation.
2. Record the verification date in the adapter documentation or ADR.
3. Implement signature verification and idempotency first.
4. Persist the original provider event encrypted only when legally permitted.
5. Acknowledge webhooks quickly and process asynchronously.
6. Implement retries with bounded exponential backoff.
7. Create dead-letter handling.
8. Build reconciliation jobs for missed events.
9. Add sandbox/test-account integration tests.
10. Never assume historical-message access is universally available.

## 12. Database and migrations

- Use forward-only production migrations with a documented rollback or remediation plan.
- Never delete or rename a populated column in one release.
- Use expand/migrate/contract for destructive schema changes.
- Every migration must be reviewed for locking and tenant impact.
- Seed data must contain no real customer information.
- Do not use SQLite as a production substitute for PostgreSQL.

## 13. Testing requirements

At minimum:

- Unit tests for domain rules and deterministic metrics.
- Contract tests for canonical message schemas.
- Webhook verification and idempotency tests.
- Authorization and cross-tenant access tests.
- PII redaction tests, including false-negative test cases.
- LLM output validation tests using recorded sanitized fixtures.
- Migration tests.
- End-to-end tests for the highest-value user path.

Tests must not call paid APIs by default. External calls require explicit opt-in.

## 14. Git and change safety

- One coherent task per branch/commit series.
- Never rewrite shared history.
- Never commit generated secrets or customer data.
- Do not auto-merge.
- Do not deploy automatically unless the user explicitly requests it.
- Show diffs for security-sensitive changes.
- Add an ADR before introducing a new datastore, framework, provider, or cross-cutting pattern.

## 15. Current execution priority

Follow `TASKS.md`. Do not jump to Instagram, autonomous follow-up, or advanced forecasting before the platform foundation and first official channel are complete.

The immediate goal is not a visual demo. It is a secure, testable foundation that can onboard the first paid design partner without corrupting data, leaking tenant information, or making unverifiable claims.
