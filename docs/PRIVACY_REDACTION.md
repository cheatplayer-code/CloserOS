# Privacy redaction

Block LM implements deterministic local detection, placeholder sanitization, encrypted
sanitized persistence, and AI eligibility gating. See ADR-0014 and ADR-0005.

## Scope

Implemented in Block LM:

- stdlib-only detector (`lm-detector-v1`) and sanitizer (`lm-policy-v1`);
- `content_sanitizations` and `content_sanitization_category_counts` tables
  (revision `d1f3a5c7e9b2`);
- real `content.redact` outbox handler for `message` and `message_edit_event`;
- encrypted `sanitized_message` rows linked from sanitization records;
- audit events `content.sanitization.completed` and `content.sanitization.blocked`.

Not implemented in Block LM:

- external AI calls or `message.analyze` handler;
- name/address/medical NER or ML-based detectors;
- production malware or DLP scanner adapters;
- HTTP routes to read raw or sanitized message bodies;
- mapping vault or tokenization beyond stable placeholders.

## Detector categories

| Category | Severity | Rule examples | Placeholder |
|----------|----------|---------------|-------------|
| `email` | high | `email_basic` | `[REDACTED_EMAIL]` |
| `telephone` | high | `phone_digit_count` (10–15 digits) | `[REDACTED_PHONE]` |
| `payment_card` | critical | `payment_card_luhn` | `[REDACTED_PAYMENT_CARD]` |
| `iban` | high | `iban_mod97` | `[REDACTED_IBAN]` |
| `national_id` | critical | `kz_iin_bin_checksum` (12-digit KZ ID) | `[REDACTED_NATIONAL_ID]` |
| `ip_address` | medium | `ipv4_stdlib`, `ipv6_stdlib` | `[REDACTED_IP]` |
| `jwt` | critical | `jwt_three_segment` | `[REDACTED_CREDENTIAL]` |
| `bearer_token` | critical | `bearer_prefix` | `[REDACTED_CREDENTIAL]` |
| `api_secret` | critical | `api_secret_assignment` | `[REDACTED_CREDENTIAL]` |
| `password_assignment` | critical | `password_assignment` | `[REDACTED_CREDENTIAL]` |
| `url_credential` | high | `url_userinfo` | `[REDACTED_CREDENTIAL]` |
| `control_content` | critical | `control_content` | `[REDACTED_CREDENTIAL]` |

Findings persist metadata only: category, start/end offsets, severity, and
`rule_id`. Matched substrings are never stored in PostgreSQL, logs, or audit
payloads.

## Limitations

The detector targets **high-confidence structured identifiers and credentials**
only. It does **not** detect:

- arbitrary person names;
- postal or street addresses;
- medical or health-related narratives;
- every possible secret format.

Operational implication: a clean detector result does not prove a message is free
of personal or confidential content. Downstream external AI remains gated by tenant
policy, purpose limitation, and fail-closed rules in ADR-0005.

Maximum input size: 256 KiB UTF-8 after decode. Text is NFC-normalized before
matching.

## Sanitization flow

```text
raw encrypted content (RAW_MESSAGE, UTF-8)
        |
        v
content.redact handler
  decrypt (purpose=redaction, audited)
        |
        v
detect_sensitive_data (initial pass)
        |
        +-- invalid UTF-8 / control chars --> BLOCKED
        |
        v
apply category placeholders (right-to-left span safe via ordered replacement)
        |
        v
detect_sensitive_data (post-sanitization pass)
        |
        +-- any remaining finding --> BLOCKED (unresolved_restricted)
        |
        v
encrypt sanitized text (SANITIZED_MESSAGE) when eligible
        |
        v
append content_sanitizations + category_counts + audit
        |
        v
optional metrics.recalculate enqueue (eligible only)
```

### Analysis eligibility

| Code | Sanitized row | External AI |
|------|---------------|-------------|
| `eligible` | written when findings were redacted | may proceed only after ADR-0005 gates |
| `blocked` | not written | must not run |
| `not_applicable` | not written (no findings) | policy-dependent; redaction gate satisfied |

### Failure codes

| Code | Typical cause |
|------|----------------|
| `invalid_utf8` | bytes are not valid UTF-8 |
| `control_content` | disallowed control characters in input |
| `unresolved_restricted` | findings remain after placeholder pass |
| `unsupported_encoding` | raw content is not UTF-8 (handler-level) |
| `processing_failed` | reserved for future catastrophic handler errors |

Blocked results still persist a completed sanitization row with
`analysis_eligibility=blocked` for audit and idempotency.

## Persistence

### `content_sanitizations`

- Tenant-scoped composite FKs to `encrypted_contents` for source and optional
  sanitized content.
- Unique `(tenant_id, source_content_id, policy_version)` prevents duplicate
  completed work per policy generation.
- Stores `detector_version`, finding counts, eligibility, optional `failure_code`,
  and timestamps.

### `content_sanitization_category_counts`

- One row per `(sanitization_id, category)` with positive count.
- Sum of category counts equals `total_finding_count` on completed rows.

## `content.redact` handler

Job reference:

- `resource_type`: `message` or `message_edit_event`
- `resource_id`: canonical row UUID
- `secondary_id`: expected `content_id` (validated against parent row)

Behavior:

1. Skip if a completed sanitization exists for `(source_content_id, policy_version)`.
2. Load and validate parent row under tenant lock.
3. Decrypt raw content; reject non-`RAW_MESSAGE` kinds permanently.
4. Block with audit when encoding is not UTF-8.
5. Run `sanitize_text`; encrypt sanitized output only when `eligible`.
6. Commit sanitization row and audit atomically.
7. Enqueue metrics recalculation on success when eligible.

Duplicate job delivery is safe: unique constraints and early completed-row checks
make the handler idempotent.

## AI boundary

```text
ingestion --> raw ciphertext --> content.redact --> eligibility decision
                                                      |
                        +-----------------------------+-----------------------------+
                        |                             |                             |
                   blocked                     not_applicable                    eligible
                        |                             |                             |
                        v                             v                             v
              no external AI                   policy gates only            sanitized ciphertext
              on this content                  for non-redacted paths       available for gated
                                                                            message.analyze (Block NO+)
```

Block LM never calls external LLM providers. It produces sanitized ciphertext and
eligibility metadata consumed by later analysis blocks. Sanitized text must still
pass tenant policy, egress controls, and output validation before leaving the
approved environment.

## Related documents

- `docs/adr/ADR-0014-deterministic-redaction-and-metrics.md`
- `docs/adr/ADR-0005-sanitized-only-external-ai.md`
- `docs/ENCRYPTED_CONTENT.md`
- `docs/OUTBOX.md`
