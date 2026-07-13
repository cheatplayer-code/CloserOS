# Observability

CloserOS logs **metadata only** — no message bodies, tokens, or raw PII.

## Logs

Structured fields (examples):

- `correlation_id` (from `RequestCorrelationMiddleware`)
- `tenant_id` (UUID, when authorized context exists)
- `outbox_job_id`, `job_kind`, `attempt`
- HTTP method, route template, status, duration_ms
- provider adapter name and outcome class (never raw payloads)

Application code must not `print()` secrets or conversation text.

## Health endpoints

| Endpoint | Service | Meaning |
|----------|---------|---------|
| `GET /health` | API | Process up |
| `GET /ready` | API | Database reachable |
| process exit code | Worker | Fatal configuration or crash |

Railway uses `/ready` for API deploy health (`infra/railway/railway.api.toml`).

## Metrics (staging baseline)

Until a metrics backend ADR is accepted, operators rely on:

- Railway/Vercel dashboards (CPU, memory, restarts)
- Supabase query insights (connection count, slow queries)
- Redis `INFO` and stream length for `OUTBOX_STREAM`
- Application audit log queries for security-sensitive actions

Target metrics for Block Z:

- outbox publish lag and processing latency;
- dead-letter job count;
- webhook acceptance rate vs verification failures;
- AI budget utilization per tenant (metadata only).

## Tracing

Distributed tracing is deferred. `correlation_id` must propagate from HTTP to
outbox jobs where handlers support it.

## Error reporting

Configure a jurisdiction-approved error reporting SaaS in Block Z. Until then,
capture stack traces in platform logs with PII scrubbing filters.

## Alerting thresholds (recommended staging)

| Signal | Threshold | Action |
|--------|-----------|--------|
| API `/ready` failures | 3 consecutive | Page on-call |
| Worker restarts | >5 in 15 min | Inspect logs, Redis, DB |
| Outbox stream length | monotonic growth 30 min | Scale worker / investigate DLQ |
| Trivy CRITICAL in CI | any | Block deploy |

## Related documentation

- `docs/INCIDENT_RESPONSE.md`
- `docs/WORKER_OPERATIONS.md`
- `AGENTS.md` observability section
