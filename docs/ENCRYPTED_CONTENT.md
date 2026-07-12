# Encrypted content

Block HI (envelope encryption foundation) stores raw message bodies, sanitized
message bodies, and optional provider webhook payloads as tenant-bound ciphertext
in PostgreSQL. Canonical tables reference encrypted rows through `content_id`
only.

## Scope

Implemented in Block HI:

- framework-independent `EncryptedContent` domain with kind, encoding, and access
  purpose enums;
- AES-256-GCM envelope encryption through `DataKeyCryptography` and `KeyProvider`
  ports;
- `encrypted_contents` table (revision `e7a1c3d5f9b2`) with composite
  `(tenant_id, id)` uniqueness;
- tenant-scoped composite foreign keys from `messages`, `message_edit_events`, and
  `webhook_events.encrypted_payload_content_id`;
- `ContentEncryptionService` for encrypt, audited decrypt, and rewrap;
- atomic commands that persist encrypted content, canonical rows, outbox jobs, and
  audit events in one transaction;
- audited actions: `encrypted_content.stored`, `encrypted_content.accessed`,
  `encrypted_content.key_rewrapped`.

Not implemented in Block HI:

- production KMS/HSM adapter;
- retention deletion worker;
- redaction pipeline that writes `sanitized_message` rows;
- HTTP routes for content access;
- bulk key-rotation scheduler.

## Lifecycle

```text
plaintext (in-memory only)
        |
        v
encrypt_and_persist  --->  encrypted_contents row
        |                  (ciphertext, nonces, wrapped DEK, key_version)
        v
canonical reference  --->  messages.content_id
                           message_edit_events.content_id
                           webhook_events.encrypted_payload_content_id
        |
        v
load_and_decrypt (audited, purpose-gated)
        |
        v
rewrap_content_key (rotation)  --->  updated wrapped DEK + key_version
        |
        v
retention expiry  --->  future deletion worker (Block JK+)
```

### Store

1. Validate tenant is active and plaintext size for the kind.
2. Derive `expires_at` from tenant retention policy.
3. Generate per-content DEK, encrypt plaintext with content AAD.
4. Wrap DEK with active KEK and key-wrap AAD.
5. Insert `encrypted_contents` in the same transaction as the canonical parent
   row and any dependent outbox job.

### Access

Decrypt requires:

- tenant-scoped repository lookup;
- permitted `ContentAccessPurpose` for the content kind;
- append of `encrypted_content.accessed` with metadata-only fields (`content_kind`,
  `key_version_code`, `reason_code`).

Purposes by kind:

| Kind | Permitted purposes |
|------|-------------------|
| `raw_message` | `redaction`, `ai_analysis`, `audit_review`, `retention_deletion` |
| `sanitized_message` | `ai_analysis`, `audit_review`, `retention_deletion` |
| `provider_payload` | `webhook_normalization`, `audit_review`, `retention_deletion` |

### Rewrap

Key rotation re-encrypts only the wrapped DEK. Content ciphertext and content
nonce are unchanged. Rewrap appends `encrypted_content.key_rewrapped` with
`previous_status` and `new_status` key-version codes.

## Cryptography summary

| Element | Size / value |
|---------|-------------|
| DEK | 32 bytes (AES-256) |
| Content nonce | 12 bytes |
| Key-wrap nonce | 12 bytes |
| Algorithm | `aes_256_gcm` |
| AAD version | `1` (current) |
| Max plaintext | 256 KiB (`raw_message`, `sanitized_message`); 1 MiB (`provider_payload`) |

Content AAD:

```text
closeros-content-v1|{tenant_id}|{content_id}|{kind}|{encoding}
```

Key-wrap AAD:

```text
closeros-dek-wrap-v1|{tenant_id}|{content_id}|{key_version}
```

## Key management ownership

| Concern | Owner |
|---------|-------|
| KEK generation, storage, and rotation policy | Platform / security operations |
| `KeyProvider` adapter implementation | Infrastructure layer |
| Per-content DEK generation | `AesGcmContentCryptography` at encrypt time |
| `key_version` on each row | Written at encrypt/rewrap; used at unwrap |
| Production adapter selection and jurisdiction | Accepted ADR + deployment runbook |
| Bulk rewrap scheduling | Future operations worker |
| Local/test keys | `StaticKeyProvider` only — never production |

Production composition must call `require_production_key_provider` and inject an
explicit adapter. Missing production configuration fails closed.

KEK material is loaded from environment variables or an approved secrets manager
in the adapter implementation. KEKs are never committed to the repository, stored
in PostgreSQL, or passed to external LLM providers.

## No plaintext in database or logs

PostgreSQL stores:

- `ciphertext`, `content_nonce`, `wrapped_data_key`, `key_wrap_nonce`;
- metadata: `kind`, `encoding`, `algorithm`, `key_version`, `aad_version`,
  `plaintext_byte_length`, `created_at`, `expires_at`.

PostgreSQL does **not** store plaintext message bodies, sanitized text, or raw
provider JSON.

Logs, traces, metrics, and audit metadata must not contain:

- plaintext content;
- ciphertext or wrapped DEK bytes;
- DEK or KEK material;
- decryption error details that could aid ciphertext manipulation.

Safe audit metadata uses allowlisted scalar codes only (`content_kind`,
`key_version_code`, `reason_code`). See `docs/AUDIT_LOG.md`.

Exception messages from encryption services are generic (`encrypted content is
unavailable`, `encrypted content persistence failed`).

## Tenant isolation

- Every row includes `tenant_id`.
- Composite uniqueness and foreign keys include `tenant_id`.
- Repository lookups require both `tenant_id` and `content_id`.
- AAD binds `tenant_id` into both content and key-wrap contexts.

Cross-tenant content access tests are release-blocking.

## Related documents

- `docs/adr/ADR-0012-envelope-encryption-and-transactional-outbox.md`
- `docs/OUTBOX.md`
- `docs/SECURITY_COMPLIANCE.md`
- `docs/AUDIT_LOG.md`
- `packages/backend/src/closeros/infrastructure/migrations/README.md`
