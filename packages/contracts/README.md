# CloserOS Contracts (`@closeros/contracts`)

Versioned, provider-neutral canonical entity contracts shared across CloserOS
services and clients.

## Layout

```text
packages/contracts/
  schemas/v1/          JSON Schema (draft 2020-12) per canonical entity
  src/v1/              Hand-written TypeScript types and enums
  fixtures/v1/valid/   Synthetic passing examples
  fixtures/v1/invalid/ Synthetic failing examples
```

Canonical entities mirror `packages/backend/src/closeros/domain/`:

- channel connection
- lead
- sales case
- conversation thread
- message
- message edit / deletion / delivery-status events
- manager assignment
- CRM outcome
- webhook event

Contracts intentionally exclude message bodies (`body`, `text`, `content`).
`content_id` is an opaque encrypted-storage reference only.

## Versioning rules

1. **Major folder = breaking boundary.** New incompatible shapes go in `schemas/v2/`
   and `src/v2/`. Never rewrite published v1 files in place.
2. **`schema_version` is required** on every entity and is pinned with JSON Schema
   `const` (v1 uses `"1.0"`).
3. **Backward-compatible v1 changes** (allowed without a new major folder):
   - add optional properties;
   - add new enum values at the end of a list (never rename or remove values);
   - clarify descriptions and validation bounds that only narrow invalid data.
4. **Breaking changes** (require `v2`):
   - remove or rename required fields;
   - change field types;
   - remove enum values;
   - move provider-specific data out of `adapter_metadata` into core fields.
5. **Tenant isolation is mandatory.** Every tenant-owned record includes `tenant_id`
   (UUID). Contract tests fail if it is removed.
6. **Provider fields stay in `adapter_metadata`.** Keys are bounded strings; values are
   JSON scalars only (`string`, `integer`, `boolean`, `null`). Sensitive key fragments
   (`body`, `text`, `content`, `token`, etc.) are rejected.
7. **Timestamps are timezone-aware ISO 8601** strings with `Z` or a numeric offset.
8. **No code generation.** TypeScript types are maintained manually beside JSON Schema.
   `src/v1/compatibility.test.ts` guards drift.
9. **Fixtures are synthetic only.** Never commit real customer payloads.

## Scripts

```bash
corepack pnpm --filter @closeros/contracts test
corepack pnpm --filter @closeros/contracts typecheck
```

Root `pnpm test` runs package tests recursively via the monorepo Vitest install.

## Consumption

```ts
import {
  ChannelConnectionV1,
  ProviderKind,
  SCHEMA_VERSION_V1,
} from "@closeros/contracts";
```

JSON Schema files are exported under `@closeros/contracts/schemas/v1/*` for validators
and documentation tooling outside this package.
