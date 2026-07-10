# Security and Compliance Requirements

This document defines engineering constraints. It is not a substitute for a written opinion from qualified Kazakhstan counsel.

## 1. Release gate

No real customer conversations may enter production until:

- data-flow mapping is complete;
- Kazakhstan hosting and backup locations are verified;
- customer agreement and DPA are signed;
- lawful basis, notices, and responsibilities are documented;
- retention periods are configured;
- incident response exists;
- access controls are tested;
- external subprocessors are approved;
- deletion and export workflows are tested.

## 2. Data classification

### Public
Marketing content intentionally public.

### Internal
Non-public product and operational data.

### Confidential
Business configuration, analytics, and non-public knowledge documents.

### Personal data
Identifiers and conversation content associated with a person.

### Sensitive/restricted
Health, children, biometric, financial credentials, legal case details, migration status, government identifiers, and other legally or contractually restricted categories.

Restricted data must not be sent to an external LLM unless a separately approved legal and technical design explicitly permits it.

## 3. Data-location principle

Until legal counsel approves otherwise:

- raw conversations stay in Kazakhstan;
- primary database stays in Kazakhstan;
- object storage stays in Kazakhstan;
- backups stay in Kazakhstan;
- production logs stay in Kazakhstan;
- raw exports stay in Kazakhstan;
- external LLM receives only approved sanitized text.

Sanitized text remains potentially pseudonymized personal data until qualified Kazakhstan counsel confirms otherwise. Redaction does not by itself make data anonymous or remove location, purpose, vendor-review, retention, and access-control requirements.

The implementation must make data location auditable.

## 4. Data minimization

Ingest only fields necessary for:
- conversation reconstruction;
- assigned manager;
- timing metrics;
- evidence;
- CRM outcome;
- lawful follow-up workflow.

Do not collect contacts, attachments, profile data, or full CRM records “just in case.”

## 5. Local redaction

Before an external LLM call:

1. classify content;
2. detect direct identifiers;
3. detect restricted categories;
4. replace approved identifiers with stable placeholders;
5. run residual-risk checks;
6. block uncertain or restricted cases;
7. record detector version and policy result.

Examples:
- `[PERSON_1]`
- `[PHONE_1]`
- `[EMAIL_1]`
- `[ADDRESS_1]`
- `[DOCUMENT_ID_1]`

The mapping vault is encrypted and unavailable to the LLM subsystem.

## 6. Access control

Requirements:
- least privilege;
- tenant-scoped roles;
- MFA for privileged roles;
- short-lived sessions;
- server-side checks;
- audited privileged access;
- support access disabled by default;
- just-in-time support access with tenant approval where possible.

## 7. Secret and token handling

- Store provider tokens encrypted.
- Never expose tokens to the frontend.
- Never log Authorization headers.
- Support rotation and revocation.
- Use separate credentials per environment.
- Production secrets must not live in `.env` files on developer laptops.

## 8. Encryption

- TLS in transit.
- Encryption at rest for disks and object storage.
- Application-level encryption for raw message content and provider tokens.
- Document key-management ownership and rotation.
- Backups encrypted independently.

Do not invent custom cryptography.

## 9. Logging

Allowed:
- IDs;
- event types;
- timestamps;
- latency;
- status;
- error class;
- correlation ID;
- tenant ID where policy permits.

Prohibited:
- message text;
- names;
- phone numbers;
- email addresses;
- access tokens;
- webhook secrets;
- LLM prompts containing customer text;
- uploaded documents.

## 10. Retention

Retention is configurable by data category.

The product must support:
- raw-message retention;
- sanitized-message retention;
- AI-output retention;
- audit-log retention;
- backup expiration;
- deletion after contract end;
- legal hold only when valid.

Deletion must be observable and resumable.

## 11. Consent and notices

The customer business is responsible for confirming its authority to provide data and monitor workers/customers. CloserOS must provide contractual and product controls, not assume the responsibility disappeared.

Before connection, record customer confirmation of:
- customer notice;
- employee notice;
- automated analysis disclosure where required;
- external processor disclosure;
- approved purposes;
- retention;
- outbound-message authority.

Do not treat a checkbox as sufficient if the underlying legal basis is missing.

## 12. Employee monitoring safeguards

- Scores are advisory.
- Findings include evidence.
- Human review and appeal are available.
- No automated termination, salary reduction, or punishment.
- Access to individual scorecards is role-restricted.
- Measurement window and sample size are visible.
- Bias and language-performance checks are required.

## 13. Incident response

Minimum runbook:
- detect;
- contain;
- preserve evidence;
- assess affected tenants and data;
- rotate credentials;
- notify internal owner and counsel;
- determine legal notification duties and deadlines;
- communicate with customers;
- remediate;
- document post-incident actions.

Run a tabletop exercise before paid production onboarding.

## 14. Security testing

Required before production:
- dependency scanning;
- secret scanning;
- SAST;
- authentication tests;
- cross-tenant authorization tests;
- webhook replay tests;
- rate-limit tests;
- backup restore test;
- deletion test;
- PII redaction tests;
- abuse-case review;
- external penetration test when budget permits.

## 15. Vendor review

Every processor or infrastructure vendor requires:
- purpose;
- data categories;
- location;
- retention;
- security controls;
- subprocessor list;
- incident terms;
- deletion process;
- contract/DPA;
- exit plan.

Free tiers are not automatically acceptable.

## 16. Prohibited shortcuts

- uploading raw chats to public AI chat interfaces;
- using production customer data in local testing;
- storing customer exports in shared Google Drive by default;
- copying production databases to developer machines;
- browser scraping of messaging applications;
- hard-coded secrets;
- sending raw errors containing customer data to third-party monitoring.
