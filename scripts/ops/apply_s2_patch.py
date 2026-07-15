"""Apply bounded S2 edits to large existing files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8-sig")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected 1 match, found {count}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


replace_once(
    "apps/api/src/closeros_api/reply_suggestion_router.py",
    '''        provider_code=run.provider_code,
        model_code=run.model_code,
        cost_status=run.cost_status.value,
''',
    '''        provider_code=run.provider_code,
        model_code=run.model_code,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        latency_milliseconds=run.latency_milliseconds,
        cost_status=run.cost_status.value,
        estimated_cost_microunits=run.estimated_cost_microunits,
''',
    "serialize non-sensitive provider telemetry",
)

replace_once(
    "PROJECT_STATUS.md",
    '''## Current phase

**Block V1-3 — Reply suggestion copilot and Buyer Memory** (branch
`feat/v1-reply-memory`; includes V1-1 + V1-2; **not** production-ready)

| Status | Detail |
|--------|--------|
| Baseline | `master` at `bf9915e` (Z0 merged) |
| This branch | Grounded reply candidates, Buyer Memory, encrypted draft-on-select |
| Prior | V1-1 integrity + V1-2 catalog grounding carried on this branch |
| Live providers | **None** (synthetic AI in CI; optional DeepSeek smoke gated) |

## Completed implementation blocks

| Block | Scope | Status |
|-------|-------|--------|
| **FG**–**Z0** | Foundation through staging bootstrap | Merged on master |
| **V1-1** | Integrity foundation defect repair | Implemented on this branch |
| **V1-2** | Structured catalog + grounding | Implemented on this branch |
| **V1-3** | Reply copilot + Buyer Memory | **In progress on `feat/v1-reply-memory`** |

## Remaining block

**Z only** — live provider sandbox sign-off, production KMS vendor selection,
staging/production deployment (Supabase/Railway/Vercel), backup/restore drill,
security release gate, legal/compliance approval, design-partner pilot, go/no-go.

Z0 operator tooling (`scripts/ops/bootstrap_tenant.py`, `seed_synthetic_demo.py`,
`synthetic_smoke.py`) supports synthetic verification **without** live providers.
No production readiness claim.
''',
    '''## Current phase

**Block S2 — managed staging activation and live DeepSeek sign-off tooling**
(branch `feat/s2-staging-deepseek-signoff`; **not** production-ready)

| Status | Detail |
|--------|--------|
| Baseline | `master` after S1 permanent DeepSeek wiring (PR #21 merged) |
| This branch | Staging preflight, live/disabled DeepSeek HTTP smoke, provider telemetry, deployment/sign-off runbook |
| Live provider code | Permanent fail-closed DeepSeek wiring merged; no PowerShell monkeypatch |
| Live cloud sign-off | Pending owner-provisioned Supabase, Railway, Vercel, and sealed staging secrets |

## Completed implementation blocks

| Block | Scope | Status |
|-------|-------|--------|
| **FG**–**Z0** | Foundation through synthetic staging bootstrap | Merged on master |
| **V1-1** | Integrity foundation defect repair | Merged on master |
| **V1-2** | Structured catalog + grounding | Merged on master |
| **V1-3** | Reply copilot + Buyer Memory | Merged on master |
| **S1** | Permanent fail-closed DeepSeek provider wiring | Merged on master (PR #21) |
| **S2** | Managed staging activation and live DeepSeek sign-off tooling | Implemented on this branch; live cloud evidence pending |

## Remaining release work

Live Supabase/Railway/Vercel provisioning and S2 evidence capture, production KMS
vendor selection and rotation drill, backup/restore drill, security release gate,
legal/compliance approval, design-partner pilot, and production go/no-go remain.

Z0/S2 operator tooling supports synthetic baseline verification, fail-closed
configuration checks, live DeepSeek acceptance, and kill-switch verification.
No production readiness claim.
''',
    "refresh current phase and block table",
)

replace_once(
    "PROJECT_STATUS.md",
    '''## Not complete (Z-only live verification)

- Live Meta WhatsApp sandbox verification.
- Bitrix24 live sandbox verification.
- Production KMS vendor live verification and key rotation drill.
- Production SMTP provider activation.
- Production Kazakhstan hosting sign-off.
- Autonomous outbound messaging.
- Remote GitHub PR CI green claim for Z0 branch (XY PR #18 passed).
- Staging/production deployment.

## Last updated

2026-07-14 (Block V1-3 reply copilot + buyer memory on `feat/v1-reply-memory`;
reply unit tests green; migration head `c3e5a7b9d1f0`; no autonomous send)
''',
    '''## Not complete (live and production verification)

- S2 cloud provisioning and captured live DeepSeek staging evidence.
- Live Meta WhatsApp sandbox verification.
- Bitrix24 live sandbox verification.
- Production KMS vendor live verification and key rotation drill.
- Production SMTP provider activation.
- Production Kazakhstan hosting sign-off.
- Backup/restore drill against the selected managed PostgreSQL tier.
- Security/legal release gate and design-partner pilot.
- Autonomous outbound messaging (explicitly out of scope).

## Last updated

2026-07-16 (S1 merged; S2 staging preflight and live/disabled DeepSeek sign-off
tooling implemented on `feat/s2-staging-deepseek-signoff`; cloud evidence pending;
no autonomous send)
''',
    "refresh remaining work and last updated",
)

print("S2 bounded patch applied")
