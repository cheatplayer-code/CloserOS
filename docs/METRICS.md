# Deterministic metrics

Block LM computes tenant- and manager-scoped operational metrics from canonical
metadata only. Message bodies and sanitized text are never read. See ADR-0014.

## Scope

Implemented in Block LM:

- `MetricsEngine` with formula version `lm-metrics-v2`;
- half-open time windows derived from tenant IANA time zones;
- immutable `metric_snapshots` and `metric_values` persistence;
- `metrics.recalculate` outbox handler;
- `MetricsEnqueueService` with per-day deduplication;
- HTTP list and manual recalculation routes;
- audit events: `metrics.recalculation.requested`, `metrics.snapshot.completed`,
  `metrics.viewed`.

Not implemented in Block LM:

- owner dashboard UI (Block RS);
- revenue-at-risk or AI-derived estimates;
- real-time streaming metrics;
- cross-tenant benchmarks.

## Content independence

Metrics source data includes:

- message direction, sender type, `received_at`, thread ID;
- conversation threads and optional sales-case links;
- manager assignments (thread or sales-case scoped);
- delivery status events;
- sales-case status updates;
- CRM outcomes linked to in-window sales cases.

No metric formula accesses `encrypted_contents`, detector output, or sanitization
eligibility. Ingestion and metrics proceed even when redaction blocks external AI
(ADR-0005).

## Time windows

All filters use **half-open intervals**: `timestamp >= window_start AND timestamp < window_end`.

| Window code | Definition |
|-------------|------------|
| `daily_{YYYY-MM-DD}` | Local midnight on date D through local midnight on D+1 |
| `rolling_30d_{YYYY-MM-DD}` | `[local midnight on D+1 minus 30 days, local midnight on D+1)` |

Local boundaries use the tenant `time_zone` (`zoneinfo` IANA name).

The `metrics.recalculate` handler computes both windows for the tenant-local
calendar date derived from the job `created_at` timestamp.

## Scopes

| Scope | `manager_user_id` | Thread set |
|-------|-------------------|------------|
| `tenant` | `null` | all conversation threads loaded for the window |
| `manager` | required | threads attributed to the manager |

Manager attribution (shared helper `resolve_manager_metric_scope`):

V1 rule — attribute a thread or sales case to the **latest eligible assignment
effective at the requested cutoff** (`assigned_at <= window_end`):

1. Prefer direct `conversation_thread_id` assignment when present.
2. Else use assignment on the thread's `sales_case_id`.
3. When multiple assignments compete, keep the latest `assigned_at`; tie-break by
   assignment UUID lexicographic order.
4. Direct sales-case assignments (no thread) contribute to manager
   `sales_case_ids` for appointment/won/lost metrics even without messages.
5. Unassigned threads/cases are excluded from manager scope but remain in
   tenant scope.

Manager CRM metrics (appointments, won, lost, conversion) are scoped only to
`manager_sales_case_ids`, never to all tenant sales cases in the window.

## Metric keys and formulas

Unless noted, values are non-negative integers. Optional keys are omitted when the
formula cannot produce a defined result (for example zero denominator).

### Volume and thread counts

| Key | Formula |
|-----|---------|
| `inbound_message_count` | Count of messages in window with `direction=inbound` and `sender_type=customer` |
| `outbound_manager_message_count` | Count with `direction=outbound` and `sender_type=manager` |
| `active_thread_count` | Count of distinct threads in scope (from loaded thread set) |
| `inbound_thread_count` | Distinct threads with at least one inbound customer message in window |
| `responded_thread_count` | Inbound threads where the earliest outbound manager message after the earliest inbound customer message exists in the loaded message set |
| `unresponded_thread_count` | `inbound_thread_count - responded_thread_count` |
| `first_response_sample_count` | Count of per-thread first-response latency samples (seconds, integer) |

First-response latency for a thread:

1. Sort messages by `(received_at, id)`.
2. Find earliest inbound customer message.
3. Find earliest outbound manager message strictly after that timestamp.
4. Latency = integer seconds difference; negative latencies are skipped.

### Response rate (basis points)

| Key | Formula |
|-----|---------|
| `response_rate_basis_points` | `floor(responded_thread_count * 10_000 / inbound_thread_count)` when `inbound_thread_count > 0`; omitted otherwise |

Stored with `numerator=responded_thread_count`, `denominator=inbound_thread_count`.
Valid range: 0–10_000 inclusive.

### Latency percentiles (seconds)

Computed on the multiset of first-response latencies (integer seconds).

| Key | Algorithm |
|-----|-----------|
| `median_first_response_seconds` | Sort ascending. Odd count: middle element. Even count: integer average `(lower_mid + upper_mid) // 2` of the two central elements. |
| `p90_first_response_seconds` | Nearest-rank on sorted values: `rank = ((90 * n) + 99) // 100`, index `rank - 1` clamped to `[0, n-1]`. |

Omitted when the sample count is zero.

### Delivery and pipeline counts

| Key | Formula |
|-----|---------|
| `failed_delivery_count` | Delivery status events in window with `status=failed` on in-scope threads |

### CRM-aligned counts

| Key | Formula |
|-----|---------|
| `appointment_booked_case_count` | In-scope sales cases with `status=appointment_booked` |
| `won_case_count` | CRM outcomes with `outcome_type=won` for in-scope sales cases |
| `lost_case_count` | CRM outcomes with `outcome_type=lost` for in-scope sales cases |

CRM outcomes do not infer won/lost when CRM data is absent (ADR-0004).

### Conversion rate (basis points)

| Key | Formula |
|-----|---------|
| `conversion_rate_basis_points` | `floor(won_case_count * 10_000 / (won_case_count + lost_case_count))` when denominator > 0; omitted otherwise |

Stored with explicit numerator and denominator. This is an operational ratio of
recorded CRM outcomes, not confirmed revenue.

## Snapshots

Each completed snapshot stores:

- `scope`, optional `manager_user_id`;
- `window_start`, `window_end`, `window_code`;
- `formula_version` (`lm-metrics-v2`);
- `source_watermark` — max relevant source timestamp seen while loading (≥ `window_end`);
- `computed_at` — calculation timestamp (typically job creation time);
- `status` (`completed` for LM handler output);
- child `metric_values` rows.

Identity uniqueness:

```text
(tenant_id, scope, manager_user_id, window_start, window_end, formula_version)
```

Existing completed snapshots are not overwritten; recalculation skips them.

## `metrics.recalculate`

### Enqueue

Triggered by:

- successful eligible `content.redact` completion (service actor);
- `POST /tenants/{tenant_id}/metrics/recalculate` (privileged user).

Deduplication key: `metrics_recalc_{YYYY-MM-DD}` (tenant-local date of request).

Outbox kind: `metrics.recalculate`. Reference: `resource_type=tenant`,
`resource_id=tenant_id`.

### Handler

For each built-in window:

1. Load source metadata for `[window_start, window_end)`.
2. Skip if tenant snapshot already completed for the identity tuple.
3. Compute tenant snapshot via `MetricsEngine`.
4. Repeat for each manager ID seen in assignments with `assigned_at <= window_end`.

Append `metrics.snapshot.completed` audit per new snapshot.

Worker support: `metrics.recalculate` is registered alongside JK and LM handlers in
the worker runtime.

## HTTP API

Base path prefix follows the API application mount (tenant-scoped routes below).

### List snapshots

```http
GET /tenants/{tenant_id}/metrics
```

Query parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `scope` | yes | `tenant` or `manager` |
| `manager_user_id` | when `scope=manager` | Manager user UUID |
| `window_start` | no | Filter snapshots with this window start |
| `window_end` | no | Filter snapshots with this window end |
| `formula_version` | no | Defaults to `lm-metrics-v2` |

Authorization: session cookie; roles `OWNER`, `SALES_HEAD`, or `COMPLIANCE_ADMIN`.

Response: up to 50 completed snapshots with metric key/value pairs. Non-empty
results append a `metrics.viewed` audit event.

### Request recalculation

```http
POST /tenants/{tenant_id}/metrics/recalculate
```

Requires session cookie, allowed `Origin`, and CSRF header (same pattern as other
privileged mutations).

Response: `202 Accepted` with body `{"message":"accepted"}`.

Appends `metrics.recalculation.requested` audit event.

## Versioning and replay

- Bump `lm-metrics-vN` when formulas change; old snapshots remain for audit.
- Re-run recalculation to populate new formula versions without deleting history.
- Changing tenant `time_zone` affects future window boundaries; prior snapshots
  retain the windows computed under earlier boundaries.

## Related documents

- `docs/adr/ADR-0014-deterministic-redaction-and-metrics.md`
- `docs/adr/ADR-0004-crm-outcome-authority.md`
- `docs/OUTBOX.md`
- `docs/ARCHITECTURE.md` (section 7.3)
