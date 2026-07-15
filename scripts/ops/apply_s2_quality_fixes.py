"""Apply focused lint and type-check fixes for S2."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


replace_once(
    "packages/backend/src/closeros/infrastructure/ops_encryption.py",
    '''        raise RuntimeError(
            "operator scripts cannot use static encryption in production; use the remote KMS runtime"
        )
''',
    '''        raise RuntimeError(
            "operator scripts cannot use static encryption in production; "
            "use the remote KMS runtime"
        )
''',
    "wrap production error",
)

replace_once(
    "scripts/ops/staging_preflight.py",
    "import sys\n",
    "",
    "remove unused sys import",
)
replace_once(
    "scripts/ops/staging_preflight.py",
    '''            "Supabase transaction-pooler port 6543 is not supported by the current persistent SQLAlchemy runtime; use direct or session mode on port 5432",
''',
    '''            "Supabase transaction-pooler port 6543 is not supported by the "
            "current persistent SQLAlchemy runtime; use direct or session mode "
            "on port 5432",
''',
    "wrap Supabase pooler error",
)
replace_once(
    "scripts/ops/staging_preflight.py",
    '''            "plaintext redis:// is allowed only on Railway private networking; use rediss:// otherwise",
''',
    '''            "plaintext redis:// is allowed only on Railway private networking; "
            "use rediss:// otherwise",
''',
    "wrap Redis transport error",
)
replace_once(
    "scripts/ops/staging_preflight.py",
    '''                "a DeepSeek key is present while external AI is disabled; keep it sealed and verify the kill-switch drill",
''',
    '''                "a DeepSeek key is present while external AI is disabled; "
                "keep it sealed and verify the kill-switch drill",
''',
    "wrap disabled key warning",
)
replace_once(
    "scripts/ops/staging_preflight.py",
    '''            "API and web share one origin; supported, but separate origins are expected for Railway and Vercel",
''',
    '''            "API and web share one origin; supported, but separate origins "
            "are expected for Railway and Vercel",
''',
    "wrap origin warning",
)

replace_once(
    "tests/test_deepseek_staging_smoke.py",
    "    disabled_run = {\n",
    "    disabled_run: dict[str, object] = {\n",
    "annotate disabled run",
)

replace_once(
    "apps/api/src/closeros_api/composition.py",
    '''from closeros.infrastructure.production_runtime import (
    build_production_adapter_registry,
''',
    '''from closeros.infrastructure.production_runtime import (
    ProductionSharedRuntime,
    build_production_adapter_registry,
''',
    "import production shared runtime type",
)
replace_once(
    "apps/api/src/closeros_api/composition.py",
    "from closeros.infrastructure.staging_runtime import build_staging_shared_runtime\n",
    '''from closeros.infrastructure.staging_runtime import (
    StagingSharedRuntime,
    build_staging_shared_runtime,
)
''',
    "import staging shared runtime type",
)
replace_once(
    "apps/api/src/closeros_api/composition.py",
    '''    if settings.is_production:
        shared = build_production_shared_runtime(
''',
    '''    shared: ProductionSharedRuntime | StagingSharedRuntime
    if settings.is_production:
        shared = build_production_shared_runtime(
''',
    "annotate managed API shared runtime",
)

replace_once(
    "apps/worker/src/closeros_worker/runtime.py",
    '''from closeros.infrastructure.production_runtime import (
    build_production_adapter_registry,
''',
    '''from closeros.infrastructure.production_runtime import (
    ProductionSharedRuntime,
    build_production_adapter_registry,
''',
    "import production worker shared type",
)
replace_once(
    "apps/worker/src/closeros_worker/runtime.py",
    "from closeros.infrastructure.staging_runtime import build_staging_shared_runtime\n",
    '''from closeros.infrastructure.staging_runtime import (
    StagingSharedRuntime,
    build_staging_shared_runtime,
)
''',
    "import staging worker shared type",
)
replace_once(
    "apps/worker/src/closeros_worker/runtime.py",
    '''    service_actor_id = _ingestion_service_id(settings, base.ingestion_service_id)
    if settings.is_production:
''',
    '''    service_actor_id = _ingestion_service_id(settings, base.ingestion_service_id)
    shared: ProductionSharedRuntime | StagingSharedRuntime
    if settings.is_production:
''',
    "annotate managed worker shared runtime",
)
replace_once(
    "apps/worker/src/closeros_worker/runtime.py",
    '''def _development_key_provider() -> StaticKeyProvider:
''',
    '''def _merge_production_worker_overrides(
    settings: WorkerSettings,
    overrides: WorkerRuntimeOverrides | None,
) -> WorkerRuntimeOverrides:
    """Compatibility wrapper retained for production-composition tests."""

    if not settings.is_production:
        return overrides or WorkerRuntimeOverrides()
    return _merge_managed_worker_overrides(settings, overrides)


def _development_key_provider() -> StaticKeyProvider:
''',
    "retain production merge compatibility wrapper",
)

print("S2 quality fixes applied")
