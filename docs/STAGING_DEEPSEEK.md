# Staging — DeepSeek / External AI

CloserOS uses a provider-neutral AI gateway (ADR-0015). DeepSeek is the initial
OpenAI-compatible provider. External calls remain disabled by default and the
normal API selects the live provider directly from typed configuration; no
PowerShell monkeypatch or alternate API entry point is required.

## Default staging posture

```text
AI_EXTERNAL_CALLS_ENABLED=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/
DEEPSEEK_MODEL=deepseek-v4-flash
```

With external calls disabled:

- deterministic development and CI flows use `SyntheticAiProvider`;
- production does not silently report synthetic output as live AI;
- policy, tenant, sanitization, and budget boundaries remain enforced;
- no external request is made.

## Enabling sanctioned sandbox checks

Only for approved operator sessions:

1. Obtain a sandbox API key through vendor onboarding and store it only in the
   deployment platform secret store.
2. Set `AI_EXTERNAL_CALLS_ENABLED=true` on worker and API.
3. Set `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`.
4. Use a current model name such as `deepseek-v4-flash` or
   `deepseek-v4-pro`; CloserOS does not default to deprecated aliases.
5. Confirm the test tenant AI policy allows `reply.suggestion`.
6. Run with metadata-only logging; never log prompts, model output bodies, or
   bearer keys.

Enabling external calls with a missing key, model, or invalid non-HTTPS base
URL fails API startup closed. It never falls back to synthetic output.

## Data boundary

Only **sanitized** text may leave the jurisdiction to an external model. Raw
encrypted message bodies, provider credentials, and unrelated tenant data never
go to DeepSeek. Provider responses still pass strict evidence, product,
commercial-action, PII, link, and chain-of-thought validation before candidates
are persisted.

Candidate selection creates an encrypted outbound **draft** only. Existing human
approval remains mandatory; S1 does not introduce autonomous sending.

See `docs/AI_GATEWAY.md`, `docs/PRIVACY_REDACTION.md`, `docs/REPLY_COPILOT.md`,
and ADR-0005.

## Staging checklist before enabling

- [ ] Legal/vendor review recorded
- [ ] Tenant budget limits configured
- [ ] Kill switch tested (`AI_EXTERNAL_CALLS_ENABLED=false`)
- [ ] Startup failure tested with missing `DEEPSEEK_API_KEY`
- [ ] Actual provider/model/token/latency metadata verified in
      `reply_suggestion_runs`
- [ ] No real customer conversations in staging tenant
- [ ] Incident contacts listed in `docs/INCIDENT_RESPONSE.md`

## Related variables

Documented in `docs/ENVIRONMENT_VARIABLES.md` and `.env.example`.
