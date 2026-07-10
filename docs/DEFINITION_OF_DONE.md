# Definition of Done

## Feature-level

A feature is done only when:

- acceptance criteria pass;
- types and schemas are explicit;
- authorization is implemented;
- tenant isolation is tested;
- errors are handled;
- idempotency is addressed where relevant;
- logs contain no prohibited data;
- tests pass;
- docs are updated;
- `PROJECT_STATUS.md` is updated.

## Integration-level

An integration is done only when:

- official documentation was verified and date recorded;
- authorization and revocation work;
- least-privilege permissions are documented;
- webhook signatures are verified;
- duplicate and out-of-order events are tested;
- retries and reconciliation exist;
- transactional outbox publication and recovery are tested where accepted events or state changes enqueue work;
- token expiration is handled;
- connection health is visible;
- sandbox tests pass;
- provider policy constraints are enforced.

## AI feature-level

An AI feature is done only when:

- external input is sanitized;
- restricted content is blocked;
- output uses a validated schema;
- taxonomy is controlled;
- evidence IDs are validated;
- prompt and rubric versions are stored;
- cost and latency are recorded;
- fallback exists;
- evaluation regression passes;
- human review exists for the relevant impact level.

## Production release

A release is production-ready only when:

### Reliability
- health checks;
- monitoring;
- alerting;
- retry/dead-letter behavior;
- transactional outbox recovery after API, publisher, worker, database, or queue interruption;
- reconciliation for missed provider, CRM, outbox, and processing events;
- capacity limits;
- independently encrypted backups;
- successful restore test;
- rollback/remediation plan;
- provider outage behavior.

### Security
- threat model reviewed;
- no committed secrets;
- TLS is enforced for every network path that carries credentials, personal data, or confidential data;
- encrypted tokens and raw messages;
- MFA for privileged users;
- RBAC;
- cross-tenant tests;
- rate limiting;
- webhook replay protection;
- dependency/secret scans;
- SAST runs in CI with release-blocking severity thresholds and a documented exception process;
- security incident contact.

### Privacy and compliance
- legal review completed;
- contracts and DPA ready;
- data-flow map;
- subprocessor list;
- hosting locations verified;
- retention configured;
- resumable deletion is tested across database rows, encrypted objects, derived data, indexes, caches, and backup-expiry handling;
- export tested;
- support access controlled;
- incident runbook;
- no raw PII to external LLM.

### Product integrity
- metrics drill down to evidence;
- AI content labeled;
- revenue estimates disclose assumptions;
- CRM outcomes authoritative;
- no autonomous outbound send unless separately approved;
- customer success metrics agreed.

### Operations
- on-call owner;
- support process;
- runbooks;
- deployment process;
- audit logging;
- connection-health dashboard;
- cost limits;
- customer offboarding process.

If any applicable item is missing, describe the release as pre-production or pilot, not production-ready.
