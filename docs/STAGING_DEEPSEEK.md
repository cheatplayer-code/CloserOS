# Staging — DeepSeek / External AI

CloserOS uses a provider-neutral AI gateway (ADR-0015). DeepSeek is the initial
OpenAI-compatible provider. External calls remain disabled by default and the
normal API selects the live provider directly from typed configuration; no
PowerShell monkeypatch or alternate API entry point is required.

The complete managed-staging procedure is in `docs/STAGING_SIGNOFF.md`.

## Default staging posture

```text
AI_EXTERNAL_CALLS_ENABLED=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/
DEEPSEEK_MODEL=deepseek-v4-flash
```

With external calls disabled:

- deterministic development and CI flows use `SyntheticAiProvider`;
- the production runtime does not silently report synthetic output as live AI;
- tenant, policy, sanitization, grounding, and budget boundaries remain enforced;
- no external request is made.

## Current reviewed models

Staging accepts the reviewed model names:

```text
deepseek-v4-flash
deepseek-v4-pro
```

CloserOS does not use deprecated `deepseek-chat` or `deepseek-reasoner` aliases
for staging sign-off. Start with `deepseek-v4-flash`; compare Pro only through a
separate controlled evaluation with identical fabricated inputs.

## Preflight

Before any live activation, load staging variables into a trusted operator shell
and run:

```bash
uv run python scripts/ops/staging_preflight.py --json
```

The preflight fails closed for missing key/model, non-HTTPS base URLs, deprecated
model aliases, local placeholders, and inconsistent staging origins. Secret
values are never printed.

## Enabling a sanctioned sandbox window

Only for approved operator sessions:

1. Obtain a sandbox API key through vendor onboarding and store it only in the
   Railway API service variable store.
2. Seal `DEEPSEEK_API_KEY` immediately.
3. Set `AI_EXTERNAL_CALLS_ENABLED=true` on the API service.
4. Set `DEEPSEEK_BASE_URL` and `DEEPSEEK_MODEL` explicitly.
5. Confirm the fabricated test tenant AI policy allows `reply.suggestion` and
   has a bounded staging budget.
6. Deploy and require `/ready` to remain `200`.
7. Run with metadata-only logging; never log prompts, model output bodies,
   candidate text, or bearer keys.

The Reply Copilot path is synchronous in the API. The worker does not need the
DeepSeek key for this S2 acceptance path. Do not spread the key to unrelated
services.

Enabling external calls with a missing key, model, or invalid non-HTTPS base URL
fails API startup closed. It never falls back to synthetic output.

## Acceptance smoke

Operator-only environment variables:

```text
STAGING_API_URL=https://<railway-api-domain>
STAGING_WEB_URL=https://<vercel-staging-domain>
SMOKE_USER_EMAIL=<fabricated verified user>
SMOKE_USER_PASSWORD=<password-manager value>
SMOKE_EXPECTED_TENANT_ID=<synthetic tenant UUID>
SMOKE_EXPECTED_AI_PROVIDER=openai
SMOKE_EXPECTED_AI_MODEL=deepseek-v4-flash
```

Before live activation, verify the kill switch:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py --expect-disabled
```

After enabling and deploying DeepSeek:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py
uv run python scripts/ops/deepseek_staging_smoke.py --select-candidate
```

The live smoke requires:

- run status `completed`;
- provider `openai`;
- the configured current DeepSeek model;
- positive input/output token counts;
- positive provider latency;
- at least one strictly validated candidate with evidence;
- latest-run persistence matching the generated run;
- optional selection producing an encrypted outbound `draft` only.

The script emits identifiers and non-sensitive telemetry only. It does not print
prompt text, response text, candidate text, credentials, cookies, or CSRF tokens.

## Mandatory kill-switch drill

After live evidence is captured:

1. set `AI_EXTERNAL_CALLS_ENABLED=false`;
2. deploy the API;
3. run:

```bash
uv run python scripts/ops/deepseek_staging_smoke.py --expect-disabled
```

4. confirm the run is blocked with no provider/model/candidates;
5. confirm no new DeepSeek usage for the test window.

Keep external AI disabled outside approved staging sessions until the legal,
budget, monitoring, and production release gates are complete.

## Data boundary

Only **sanitized** text may leave the jurisdiction to an external model. Raw
encrypted message bodies, provider credentials, and unrelated tenant data never
go to DeepSeek. Provider responses still pass strict evidence, product,
commercial-action, PII, link, and chain-of-thought validation before candidates
are persisted.

Candidate selection creates an encrypted outbound **draft** only. Existing human
approval remains mandatory; S2 does not introduce autonomous sending.

See `docs/AI_GATEWAY.md`, `docs/PRIVACY_REDACTION.md`, `docs/REPLY_COPILOT.md`,
and ADR-0005.

## Staging checklist before enabling

- [ ] Fabricated staging tenant only
- [ ] Tenant AI policy allows only reviewed purpose(s)
- [ ] Tenant budget limits configured
- [ ] Staging preflight passed
- [ ] Kill switch smoke passed before activation
- [ ] DeepSeek key sealed on API service only
- [ ] Startup failure tested with missing key/model in a disposable deployment
- [ ] Actual provider/model/token/latency metadata verified through the API
- [ ] Draft-only selection verified
- [ ] Kill switch re-tested after live activation
- [ ] Incident contacts listed in `docs/INCIDENT_RESPONSE.md`
- [ ] Private evidence bundle recorded without secrets or customer content

## Related documentation

- `docs/STAGING_SIGNOFF.md`
- `docs/ENVIRONMENT_VARIABLES.md`
- `.env.example`
