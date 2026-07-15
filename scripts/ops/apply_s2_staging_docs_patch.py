"""Align S2 documentation with the explicit managed staging runtime."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected 1 match, found {count}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


replace_once(
    "docs/STAGING_SIGNOFF.md",
    "APP_ENV=production\n",
    "APP_ENV=staging\n",
    "use explicit staging environment",
)
replace_once(
    "docs/STAGING_SIGNOFF.md",
    '''APP_ENCRYPTION_KEY=<sealed staging-only key>
AUTH_CSRF_SECRET=<sealed random value, at least 32 bytes>
AUTH_RATE_LIMIT_SECRET=<sealed random value, at least 32 bytes>
''',
    '''STAGING_ENCRYPTION_KEY_HEX=<sealed random 64-hex value>
STAGING_ENCRYPTION_KEY_VERSION=staging-kek-v1
STAGING_KNOWLEDGE_SEARCH_KEY_HEX=<sealed random 64-hex value>
REDIS_RATE_LIMIT_HMAC_SECRET=<sealed random value, at least 32 bytes>
AUTH_CSRF_SECRET=<sealed random value, at least 32 bytes>
AUTH_RATE_LIMIT_SECRET=<sealed random value, at least 32 bytes>
''',
    "document staging key material",
)
replace_once(
    "docs/STAGING_SIGNOFF.md",
    '''S2 proves the staging deployment and live provider path with fabricated data.
It does **not** authorize production traffic, real customer exports, autonomous
sending, or a production-readiness claim.
''',
    '''S2 proves the staging deployment and live provider path with fabricated data.
The services run with `APP_ENV=staging`: production-like HTTPS, cookies, rate
limits, feature gates, and fail-closed provider behavior, but sealed staging-only
static encryption/search keys. `APP_ENV=production` remains remote-KMS-only.
S2 does **not** authorize production traffic, real customer exports, autonomous
sending, or a production-readiness claim.
''',
    "explain staging security boundary",
)

replace_once(
    "docs/STAGING_RAILWAY.md",
    "APP_ENV=production\n",
    "APP_ENV=staging\n",
    "use staging environment on Railway",
)
replace_once(
    "docs/STAGING_RAILWAY.md",
    '''APP_ENCRYPTION_KEY=<sealed staging-only key>
AUTH_CSRF_SECRET=<sealed random value, at least 32 bytes>
AUTH_RATE_LIMIT_SECRET=<sealed random value, at least 32 bytes>
''',
    '''STAGING_ENCRYPTION_KEY_HEX=<sealed random 64-hex value>
STAGING_ENCRYPTION_KEY_VERSION=staging-kek-v1
STAGING_KNOWLEDGE_SEARCH_KEY_HEX=<sealed random 64-hex value>
REDIS_RATE_LIMIT_HMAC_SECRET=<sealed random value, at least 32 bytes>
AUTH_CSRF_SECRET=<sealed random value, at least 32 bytes>
AUTH_RATE_LIMIT_SECRET=<sealed random value, at least 32 bytes>
''',
    "document Railway staging keys",
)
replace_once(
    "docs/STAGING_RAILWAY.md",
    '''- Required variables: `DATABASE_URL`, `REDIS_URL`, `AUTH_*`,
  `APP_ENCRYPTION_KEY`, `INGESTION_SERVICE_ID`, `AUTH_ALLOWED_ORIGINS`
''',
    '''- Required variables: `DATABASE_URL`, `REDIS_URL`, `AUTH_*`,
  `STAGING_ENCRYPTION_KEY_HEX`, `STAGING_KNOWLEDGE_SEARCH_KEY_HEX`,
  `REDIS_RATE_LIMIT_HMAC_SECRET`, `INGESTION_SERVICE_ID`, and
  `AUTH_ALLOWED_ORIGINS`
''',
    "correct API required variables",
)

replace_once(
    "docs/DEPLOYMENT.md",
    "4. `APP_ENV=production` selects the fail-closed runtime path.\n",
    '''4. `APP_ENV=staging` selects the managed staging path. It uses secure
   cookies, distributed rate limits, explicit provider gates, and sealed
   staging-only keys. `APP_ENV=production` remains remote-KMS-only.
''',
    "describe staging runtime path",
)
replace_once(
    "docs/DEPLOYMENT.md",
    '''3. `APP_ENCRYPTION_KEY` and auth secrets are staging-only, sealed, and at least
   32 bytes.
''',
    '''3. `STAGING_ENCRYPTION_KEY_HEX` and
   `STAGING_KNOWLEDGE_SEARCH_KEY_HEX` are separate sealed 64-hex values;
   `REDIS_RATE_LIMIT_HMAC_SECRET` and auth secrets are sealed and at least 32
   bytes.
''',
    "correct staging secret checklist",
)

replace_once(
    "docs/ENVIRONMENT_VARIABLES.md",
    '''| `APP_ENV` | yes | `development` or `production`; staging uses `production` fail-closed runtime |
''',
    '''| `APP_ENV` | yes | `development`, `staging`, or `production`. Managed staging uses `staging`; production remains remote-KMS-only. |
''',
    "document APP_ENV staging",
)
replace_once(
    "docs/ENVIRONMENT_VARIABLES.md",
    '''| `APP_ENCRYPTION_KEY` | development / transitional staging | Staging-only envelope encryption key material. Must be at least 32 bytes, sealed, and never reused in production. **Not** a substitute for production remote KMS. |
''',
    '''| `STAGING_ENCRYPTION_KEY_HEX` | staging | Sealed 64-hex (32-byte) staging-only KEK. Never reuse in production. |
| `STAGING_ENCRYPTION_KEY_VERSION` | staging | Explicit staging key version, for example `staging-kek-v1`. |
| `STAGING_KNOWLEDGE_SEARCH_KEY_HEX` | staging | Separate sealed 64-hex key for deterministic lexical-search tokens. |
| `REDIS_RATE_LIMIT_HMAC_SECRET` | staging/production | Sealed HMAC secret of at least 32 bytes for distributed authentication rate-limit keys. |
''',
    "document staging key variables",
)

replace_once(
    ".env.example",
    '''# LOCAL DEVELOPMENT ONLY. This value must never be reused in staging or production.
# Production encryption and KMS configuration will be defined by a later accepted ADR.
# Do not generate, store, or document production keys in this file.
APP_ENCRYPTION_KEY=
''',
    '''# S2 managed staging only. Generate independent 32-byte values and store them
# as sealed Railway variables. Never commit real values or reuse them in production.
STAGING_ENCRYPTION_KEY_HEX=
STAGING_ENCRYPTION_KEY_VERSION=staging-kek-v1
STAGING_KNOWLEDGE_SEARCH_KEY_HEX=
REDIS_RATE_LIMIT_HMAC_SECRET=
''',
    "replace ambiguous encryption variable",
)

replace_once(
    "packages/backend/src/closeros/infrastructure/ops_encryption.py",
    '"""Development encryption helpers for operator scripts."""\n',
    '"""Environment-aware encryption helpers for development and staging operators."""\n',
    "update operator encryption module description",
)

print("S2 staging documentation patch applied")
