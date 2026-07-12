# Controlled CSV import

## Purpose

CSV import allows authorized tenant operators to upload historical conversation exports
with explicit lawful-source confirmation. Raw CSV bytes are encrypted at rest; PostgreSQL
stores only encrypted content references, integer column mappings, and safe row-error codes.

## Lifecycle

| Status | Meaning |
|--------|---------|
| `uploaded` | Encrypted source stored; mapping not yet confirmed |
| `ready` | Mapping validated; `csv.import` job enqueued |
| `processing` | Worker consuming rows in 250-row chunks |
| `completed` | All rows processed successfully |
| `completed_with_errors` | Finished with row-level safe errors |
| `failed` | Unrecoverable batch failure |
| `cancelled` | Cancelled before completion |

## API routes

- `POST /api/v1/tenants/{tenant_id}/csv-imports/preview` — encrypt source, return column indexes
- `POST /api/v1/tenants/{tenant_id}/csv-imports/{import_id}/start` — submit mapping, enqueue job
- `GET /api/v1/tenants/{tenant_id}/csv-imports/{import_id}` — status and paginated row errors
- `POST /api/v1/tenants/{tenant_id}/csv-imports/{import_id}/cancel` — cancel before completion

## Requirements

- Authenticated session, CSRF, exact Origin
- Role: OWNER or COMPLIANCE_ADMIN
- Header: `X-Lawful-Source-Confirmed: true`
- Body: `text/csv`, UTF-8 or UTF-8 BOM, max 10 MiB
- 1–50 columns, unique headers, max 50,000 data rows

## Required mapping fields

- `external_conversation_id`
- `external_message_id`
- `sender_type`
- `direction`
- `sent_at`
- `received_at`
- `message_text`

Optional: `reply_to_external_message_id`

## Processing

The `csv.import` handler:

1. Locks the batch and decrypts encrypted CSV with `csv_import_processing` purpose.
2. Resumes from `next_row_number`.
3. Processes 250 rows per chunk with per-chunk commit.
4. Encrypts each valid `message_text` as `raw_message` and persists immutable `Message`.
5. Enqueues `content.redact` per message.
6. Records invalid rows with safe error codes only (no row values).

## Retention

CSV source encrypted content uses the tenant raw-message retention limit.

## Production scanner

Development uses a no-op scanner. Production requires an explicit `ImportContentScanner`
adapter injection.
