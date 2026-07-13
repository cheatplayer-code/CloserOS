# Staging — DeepSeek / External AI

CloserOS uses a provider-neutral AI gateway (ADR-0015). DeepSeek is the initial
low-cost OpenAI-compatible provider, but **external calls are disabled by default**
in staging until Block Z release-gate criteria pass.

## Default staging posture

```text
AI_EXTERNAL_CALLS_ENABLED=false
DEEPSEEK_API_KEY=          # unset
DEEPSEEK_BASE_URL=         # unset
```

With external calls disabled:

- `message.analyze` jobs use the synthetic deterministic provider in CI/local mode.
- API routes reject live provider configuration that would send sanitized text
  without explicit opt-in.
- Budget and policy tables still enforce tenant isolation.

## Enabling sanctioned sandbox checks

Only for approved operator sessions:

1. Obtain a sandbox API key through vendor onboarding (not committed).
2. Set `DEEPSEEK_BASE_URL` to the official HTTPS endpoint documented by the vendor.
3. Set `AI_EXTERNAL_CALLS_ENABLED=true` on worker **and** API.
4. Confirm tenant AI policy allows analysis for a test tenant only.
5. Run with metadata-only logging; never log prompts or model output bodies.

## Data boundary

Only **sanitized** text may leave the jurisdiction to an external model.
Raw message bodies and provider tokens never go to DeepSeek.

See `docs/AI_GATEWAY.md`, `docs/PRIVACY_REDACTION.md`, and ADR-0005.

## Staging checklist before enabling

- [ ] Legal/vendor review recorded
- [ ] Tenant budget limits configured
- [ ] Kill switch tested (`AI_EXTERNAL_CALLS_ENABLED=false`)
- [ ] No real customer conversations in staging tenant
- [ ] Incident contacts listed in `docs/INCIDENT_RESPONSE.md`

## Related variables

Documented in `docs/ENVIRONMENT_VARIABLES.md` and `.env.example`.
