# ADR-0014: Deterministic local redaction and content-independent metrics

Status: Accepted
Date: 2026-07-12
Decision owners: CloserOS owners

## Context

Block HI established envelope-encrypted raw message storage and a transactional
outbox. Block JK ingests provider events and CSV rows, persists canonical message
metadata, and enqueues `content.redact` jobs without implementing the handler.

Block LM must:

- detect and redact high-confidence structured identifiers locally before any
  external AI call (ADR-0005);
- persist sanitized ciphertext separately from raw content;
- fail closed when redaction cannot prove residual safety;
- compute deterministic operational metrics from canonical metadata without reading
  message bodies;
- remain idempotent under duplicate outbox delivery and policy-version replays.

## Decision

### Deterministic local detection

- Implement a **stdlib-only** detector at version `lm-detector-v1`.
- Input is UTF-8 text up to 256 KiB, NFC-normalized before matching.
- Findings store category, byte offsets, severity, and `rule_id` only — never matched
  source text.
- Overlapping spans resolve deterministically by start position, span length,
  severity rank, then `rule_id`.
- Supported categories: email, telephone, payment card (Luhn-validated), IBAN
  (mod-97), Kazakhstan national ID (12-digit checksum), IPv4/IPv6, JWT,
  Bearer token, labeled credential assignments, URL userinfo credentials, and
  control-character content.

### Explicit limitations

The detector does **not** attempt to identify:

- arbitrary personal names;
- postal or street addresses;
- medical diagnoses or health narratives;
- all possible secrets or proprietary content.

These limitations are intentional. Absence of a finding does not mean absence of
personal or restricted data. Sanitized output remains potentially pseudonymized
personal data until qualified legal counsel confirms otherwise.

### Sanitization policy and placeholders

- Policy version: `lm-policy-v1` (bundled with detector version).
- Each category maps to a stable placeholder (for example `[REDACTED_EMAIL]`,
  `[REDACTED_CREDENTIAL]`).
- After placeholder replacement, the detector runs again. Any remaining finding
  yields `unresolved_restricted` and **blocks** external AI eligibility.
- Invalid UTF-8, control characters, and unsupported encodings fail closed.

### Sanitized encryption and persistence

- Successful sanitization encrypts placeholder text as
  `EncryptedContentKind.SANITIZED_MESSAGE` (UTF-8) in `encrypted_contents`.
- Raw source ciphertext is never modified in place.
- `content_sanitizations` records link `source_content_id` to optional
  `sanitized_content_id`, policy/detector versions, eligibility, finding counts,
  and per-category counts.
- Idempotency key: unique `(tenant_id, source_content_id, policy_version)`.
  Completed rows short-circuit duplicate `content.redact` jobs.

### AI eligibility boundary

| Eligibility | Meaning |
|-------------|---------|
| `eligible` | Sanitized ciphertext stored; content may proceed to gated external AI when tenant policy and legal gates allow. |
| `blocked` | Sanitization failed closed; no sanitized ciphertext; external AI must not run on this content. |
| `not_applicable` | No findings detected; sanitized ciphertext is not written; external AI may use other approved paths only when policy allows empty/redaction-free analysis. |

External AI still requires ADR-0005 gates (tenant policy, purpose, vendor review,
residual checks). Block LM provides the local redaction prerequisite, not
regulatory certification.

### `content.redact` handler

- Supported resources: `message`, `message_edit_event`.
- Decrypts raw content with `ContentAccessPurpose.REDACTION` (audited).
- Accepts UTF-8 `RAW_MESSAGE` only; other encodings persist a blocked record.
- Appends audit events: `content.sanitization.completed` or
  `content.sanitization.blocked`.
- On `eligible`, enqueues tenant metrics recalculation for the tenant-local
  calendar date (deduplicated).

### Content-independent deterministic metrics

- Formula version: `lm-metrics-v1`.
- Metrics read **canonical metadata only** (direction, sender type, timestamps,
  thread/case/assignment IDs, delivery status, CRM outcomes). Message bodies and
  sanitized text are never loaded.
- Windows are **half-open** `[window_start, window_end)` in the tenant IANA time
  zone.
- Built-in windows per recalculation: `daily_{YYYY-MM-DD}` and
  `rolling_30d_{YYYY-MM-DD}`.
- Scopes: `tenant` (all threads) and `manager` (threads attributed by assignment
  precedence: thread assignment beats sales-case assignment; latest `assigned_at`,
  then UUID tie-break).
- Snapshots are immutable and uniquely identified by
  `(tenant_id, scope, manager_user_id, window_start, window_end, formula_version)`.
- Rate metrics use **floor** integer basis points: `(numerator * 10_000) // denominator`.
- Latency percentiles use deterministic integer algorithms on sorted second counts:
  median (even-count average of middle pair) and nearest-rank p90.
- Optional metric keys (rates, median, p90, conversion) are omitted when the
  denominator or sample set is empty.

### `metrics.recalculate` handler

- Outbox kind: `metrics.recalculate`.
- Enqueue deduplication: one job per tenant per local calendar date
  (`metrics_recalc_{YYYY-MM-DD}`).
- Handler computes missing tenant and manager snapshots for daily and rolling-30-day
  windows; skips existing completed snapshots for the same identity.
- Appends `metrics.snapshot.completed` audit events.

### HTTP API (read and manual trigger)

- `GET /tenants/{tenant_id}/metrics` — privileged roles
  (`OWNER`, `SALES_HEAD`, `COMPLIANCE_ADMIN`); audited as `metrics.viewed`.
- `POST /tenants/{tenant_id}/metrics/recalculate` — same roles, CSRF + Origin;
  returns `202 Accepted`; audited as `metrics.recalculation.requested`.

### Schema migration

- Alembic revision `d1f3a5c7e9b2` creates `content_sanitizations`,
  `content_sanitization_category_counts`, `metric_snapshots`, and `metric_values`;
  extends outbox job kind and audit CHECK constraints.

## Alternatives considered

- **Third-party PII scanner as primary detector** — rejected for Block LM; adds
  vendor dependency, opaque behavior, and egress risk before local gates exist.
- **Optimistic masking without post-redaction scan** — rejected; false negatives on
  structured credentials remain high impact.
- **Metrics derived from sanitized text** — rejected; couples operational KPIs to
  redaction outcomes and prevents recomputation when only metadata changes.
- **Floating-point rates** — rejected; integer basis points with explicit numerator
  and denominator preserve auditability and deterministic replay.

## Consequences

- Name and address leakage may still reach external AI if later blocks skip policy
  gates; residual-risk review remains mandatory.
- Detector and policy version bumps require re-redaction jobs and new snapshot rows
  under new `formula_version` or policy keys.
- CRM-dependent conversion metrics reflect synced outcomes in-window; missing CRM
  data yields zero counts, not inferred outcomes (ADR-0004).
- Worker LM job kinds: `webhook.normalize`, `csv.import`, `content.redact`,
  `metrics.recalculate`. `message.analyze` remains a future block.

## Security and privacy impact

- Raw decrypt for redaction is purpose-gated and audited.
- Logs and audit events remain metadata-only (counts, versions, eligibility codes).
- Blocked content never writes sanitized ciphertext.
- Metrics queries do not expose message bodies.

## Migration and rollback/remediation

- Upgrade: apply `d1f3a5c7e9b2`.
- Downgrade drops LM tables and restores prior CHECK constraints; safe only on empty
  or test databases. Production rollback requires expand/migrate/contract, archival of
  audit rows referencing `content_sanitization` or `metric_snapshot`, and completion
  or dead-letter of pending `metrics.recalculate` jobs.
- Policy or detector upgrades: enqueue re-redaction under the new policy version;
  retain prior rows for audit history.

## Sources verified

- CloserOS `AGENTS.md`, `docs/SECURITY_COMPLIANCE.md`, ADR-0005, ADR-0012,
  ADR-0013 — reviewed 2026-07-12.
- Implementation: `privacy_detector.py`, `privacy_sanitizer.py`, `metrics_engine.py`,
  `content_redact_handler.py`, `metrics_recalculate_handler.py` — reviewed
  2026-07-12.
