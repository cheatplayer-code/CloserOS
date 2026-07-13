# Media Scanning

WhatsApp and future messaging adapters may receive media references before binary
content is downloaded. Block VW quarantines media metadata with
`media_reference=quarantined_pending_scan` until a scanning pipeline exists.

## Current posture (Block XY)

- Media binaries are **not** downloaded automatically in production paths.
- Placeholder text is ingested; encrypted metadata references are stored.
- Outbound media requires human approval and policy checks (VW).

## Target pipeline (Block Z hardening)

```text
Provider media URL
  → download to isolated object store (approved jurisdiction)
  → content-type + size validation
  → malware scan (ClamAV or managed scanner — vendor ADR required)
  → fail closed on scan error or positive match
  → optional transcoding/thumbnail (metadata only logs)
  → tenant-scoped availability for authorized roles
```

## Security requirements

- Scan **before** exposing binaries to operators or downstream AI.
- Encrypt at rest in object storage; separate DEKs per object where feasible.
- Never send raw media to external LLMs.
- Log scan job IDs and outcomes only — not filenames with PII or content hashes
  that could fingerprint customers without approval.

## Configuration placeholders

Environment variables reserved in `.env.example`:

- `MEDIA_SCANNER_ENABLED=false`
- `MEDIA_OBJECT_STORE_BUCKET=`
- `MEDIA_OBJECT_STORE_REGION=`

## Related documentation

- `docs/WHATSAPP_CLOUD.md`
- `docs/SECURITY_COMPLIANCE.md`
- ADR-0016 (quarantined media references)

## Operator actions when media is blocked

1. Confirm tenant policy allows manual review.
2. Inspect quarantine metadata in admin tools (no public URLs).
3. If false positive, follow incident process with vendor scanner support.
4. If true positive, retain per legal hold policy and notify compliance role.
