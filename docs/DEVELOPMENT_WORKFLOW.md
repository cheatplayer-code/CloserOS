# Development Workflow

## 1. One task at a time

Use task IDs from `TASKS.md`.

A task begins with:
- objective;
- scope;
- non-goals;
- acceptance criteria;
- security/privacy impact;
- migration impact;
- test plan.

## 2. Plan before edit

For non-trivial work, use Cursor Plan Mode first.

The plan must identify:
- files to change;
- interfaces;
- schema changes;
- failure modes;
- tests;
- documentation updates.

Do not accept a plan that says only “create backend and frontend.”

## 3. Implementation sequence

Recommended order:
1. contracts and domain types;
2. domain tests;
3. application use case;
4. infrastructure adapter;
5. interface/API;
6. integration tests;
7. UI;
8. end-to-end test;
9. docs and status.

## 4. Change size

Prefer a small vertical slice over a broad incomplete scaffold.

Bad:
- “Implement all integrations.”

Good:
- “Persist and deduplicate one verified WhatsApp test webhook event, with tests.”

## 5. Review checklist

For every change:
- Does tenant isolation hold?
- Could a secret be logged?
- Could raw PII reach an external service?
- Is the operation idempotent?
- What happens on timeout?
- What happens on retry?
- What happens out of order?
- Is authorization server-side?
- Are user-visible claims supported?
- Are migrations safe?
- Are tests meaningful?

## 6. Agent interaction

Ask Cursor to:
- inspect first;
- propose a plan;
- name assumptions;
- implement one task;
- run checks;
- show failures honestly;
- update project status.

Never ask:
- “build the full production app in one go”;
- “make it production ready” without criteria;
- “fix everything”;
- “use best practices” without reference to this repository.

## 7. Commits

Suggested format:

```text
type(scope): concise change

Task: CLS-###
Tests: ...
Risk: ...
```

Types:
- feat;
- fix;
- refactor;
- test;
- docs;
- build;
- ci;
- security.

## 8. ADRs

Create an ADR for:
- framework changes;
- new datastore;
- new external provider;
- authentication strategy;
- encryption/key strategy;
- major schema pattern;
- microservice extraction;
- cross-border processing decision.

ADR states:
- proposed;
- accepted;
- superseded;
- rejected.

## 9. Definition of failure

A task is not complete when:
- code was generated but not run;
- tests were not executed;
- a provider behavior was assumed;
- security checks are TODO;
- only the happy path works;
- migration rollback/remediation is unknown;
- docs contradict behavior;
- the agent cannot state what remains unverified.
