#!/usr/bin/env python3
"""Seed bounded synthetic demonstration data for a tenant."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros.application.atomic_content_commands import AtomicContentCommandService  # noqa: E402
from closeros.application.synthetic_demo_seed_service import (  # noqa: E402
    SyntheticDemoOwnerMissingError,
    SyntheticDemoSeedError,
    SyntheticDemoSeedResult,
    SyntheticDemoSeedService,
    SyntheticDemoTenantNotFoundError,
)
from closeros.infrastructure.database import database_url_from_env  # noqa: E402
from closeros.infrastructure.ops_database import build_integrated_uow_factory  # noqa: E402
from closeros.infrastructure.ops_encryption import (  # noqa: E402
    build_ops_content_encryption_service,
    ingestion_service_id_from_env,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed synthetic demo data for a tenant")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "").strip(),
        help="PostgreSQL URL (defaults to DATABASE_URL)",
    )
    parser.add_argument("--tenant-id", required=True, help="Target tenant UUID")
    parser.add_argument(
        "--confirm-synthetic-only",
        action="store_true",
        help="Required confirmation that only fabricated data will be written",
    )
    parser.add_argument(
        "--reset-existing-synthetic-demo",
        action="store_true",
        help="Delete previously seeded synthetic demo records before reseeding",
    )
    parser.add_argument(
        "--confirm-synthetic-reset",
        action="store_true",
        help="Required second confirmation when deleting previously seeded resources",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview reset counts without deleting or reseeding",
    )
    return parser.parse_args()


def _resolve_database_url(raw: str) -> str:
    if raw:
        return raw
    return database_url_from_env()


def _safe_result_payload(result: SyntheticDemoSeedResult) -> dict[str, object]:
    return {
        "status": result.status,
        "tenant_id": str(result.tenant_id),
        "conversation_threads": result.conversation_threads,
        "follow_up_tasks": result.follow_up_tasks,
        "managers": result.managers,
    }


def _build_service(database_url: str) -> SyntheticDemoSeedService:
    uow_factory = build_integrated_uow_factory(database_url)
    content_encryption = build_ops_content_encryption_service(uow_factory)
    return SyntheticDemoSeedService(
        uow_factory=uow_factory,
        content_encryption=content_encryption,
        atomic_commands=AtomicContentCommandService(
            uow_factory=uow_factory,
            content_encryption=content_encryption,
        ),
        service_actor_id=ingestion_service_id_from_env(),
        uuid_factory=uuid4,
        clock=lambda: datetime.now(UTC),
    )


async def _run(args: argparse.Namespace) -> int:
    if not args.confirm_synthetic_only:
        print("error: pass --confirm-synthetic-only", file=sys.stderr)
        return 2

    if args.reset_existing_synthetic_demo and not args.confirm_synthetic_reset and not args.dry_run:
        print(
            "error: reset requires --confirm-synthetic-reset "
            "(or --dry-run to preview scoped deletions)",
            file=sys.stderr,
        )
        return 5

    try:
        tenant_id = UUID(args.tenant_id)
    except ValueError:
        print("error: tenant id must be a UUID", file=sys.stderr)
        return 7

    database_url = _resolve_database_url(args.database_url)
    service = _build_service(database_url)

    if args.dry_run and args.reset_existing_synthetic_demo:
        from closeros.application.synthetic_demo_reset import (  # noqa: E402
            SyntheticDemoResetError,
            SyntheticDemoResetService,
        )
        from closeros.application.synthetic_demo_seed_service import (  # noqa: E402
            SYNTHETIC_DEMO_VERSION,
        )

        try:
            plan = await SyntheticDemoResetService(
                uow_factory=build_integrated_uow_factory(database_url),
                seed_version=SYNTHETIC_DEMO_VERSION,
            ).plan_reset(tenant_id=tenant_id)
        except SyntheticDemoResetError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        if plan is None:
            print(json.dumps({"dry_run": True, "total_resources": 0, "counts_by_type": {}}))
            return 0
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "tenant_id": str(plan.tenant_id),
                    "manifest_id": str(plan.manifest_id),
                    "total_resources": plan.total_resources,
                    "counts_by_type": plan.counts_by_type,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    try:
        result = await service.seed_demo(
            tenant_id=tenant_id,
            reset_existing=args.reset_existing_synthetic_demo,
        )
    except SyntheticDemoTenantNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    except SyntheticDemoOwnerMissingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 4
    except SyntheticDemoSeedError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(_safe_result_payload(result), indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
