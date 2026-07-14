# Reply Copilot and Buyer Memory (V1-3)

Separate bounded context for grounded reply suggestions. Not conversation
analysis findings.

## Flow

1. Seller requests suggestions for a conversation thread.
2. Service batch-loads sanitized transcript content, structured buyer memory,
   and catalog search hits.
3. Versioned prompt (`v1-reply-prompt-v1`) is built without raw encrypted bodies,
   secrets, full catalog, or unrelated tenants.
4. Existing OpenAI-compatible adapter (DeepSeek) or synthetic provider returns
   JSON with purpose `reply.suggestion`.
5. Strict validator rejects unknown evidence/products, CoT, PII, arbitrary links,
   unsupported discounts, and unsupported actions.
6. Deterministic grounding attaches `stale_stock` / `stale_price` warnings.
7. Inferred buyer-memory facts are persisted from customer_state (never
   auto-confirmed without a source message).
8. Seller selects or edits a candidate → encrypted outbound **draft** only.
9. Existing explicit approval remains required. No autonomous send.

## Cost

`cost_status=unknown` until Block 6 pricing configuration. Do not store `0` as
a known monetary cost.

## Memory

Structured facts with statuses `inferred|confirmed|rejected|expired|deleted`.
Conflicts create superseding rows; effective view prefers latest confirmed, else
high-confidence inferred, else none. Expired facts are never current.

## API

- `POST .../conversations/{thread_id}/reply-suggestions`
- `GET  .../conversations/{thread_id}/reply-suggestions/latest`
- `POST .../reply-suggestions/{run_id}/candidates/{candidate_id}/select`
- `POST .../reply-suggestions/{run_id}/reject`
- `GET  .../conversations/{thread_id}/memory`
- `GET  .../leads/{lead_id}/memory`
- `POST .../memory/{fact_id}/confirm|correct|reject`
- `DELETE .../memory/{fact_id}`

Managers are scoped to assigned conversations unless privileged.

## Tests

Deterministic CI uses `SyntheticAiProvider`. Optional live DeepSeek smoke is
skipped without `DEEPSEEK_API_KEY`.
