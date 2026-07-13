#!/usr/bin/env python3
"""Attach the first tenant and OWNER membership to a verified user."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros.application.bootstrap_tenant_service import (  # noqa: E402
    BootstrapEmailNotVerifiedError,
    BootstrapInvalidArgumentError,
    BootstrapOwnershipConflictError,
    BootstrapTenantError,
    BootstrapTenantService,
    BootstrapUserInactiveError,
    BootstrapUserNotFoundError,
)
from closeros.infrastructure.database import database_url_from_env  # noqa: E402
from closeros.infrastructure.ops_database import build_integrated_uow_factory  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first tenant for a verified owner user",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "").strip(),
        help="PostgreSQL URL (defaults to DATABASE_URL)",
    )
    parser.add_argument("--owner-email", required=True, help="Verified owner email")
    parser.add_argument("--tenant-name", required=True, help="Tenant display name")
    parser.add_argument(
        "--time-zone",
        default="Asia/Almaty",
        help="IANA time zone for the tenant",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to perform the bootstrap mutation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and return a synthetic result without writing",
    )
    return parser.parse_args()


def _resolve_database_url(raw: str) -> str:
    if raw:
        return raw
    return database_url_from_env()


def _safe_result_payload(result: object) -> dict[str, object]:
    from closeros.application.bootstrap_tenant_service import BootstrapTenantResult

    if not isinstance(result, BootstrapTenantResult):
        raise TypeError("unexpected bootstrap result type")
    return {
        "status": result.status,
        "tenant_id": str(result.tenant_id),
        "owner_user_id": str(result.owner_user_id),
        "roles": list(result.roles),
    }


async def _run(args: argparse.Namespace) -> int:
    if not args.confirm and not args.dry_run:
        print("error: pass --confirm or --dry-run", file=sys.stderr)
        return 2

    database_url = _resolve_database_url(args.database_url)
    service = BootstrapTenantService(
        uow_factory=build_integrated_uow_factory(database_url),
        uuid_factory=uuid4,
        clock=lambda: datetime.now(UTC),
    )
    try:
        result = await service.bootstrap_owner_tenant(
            owner_email=args.owner_email,
            tenant_name=args.tenant_name,
            time_zone=args.time_zone,
            dry_run=args.dry_run,
        )
    except BootstrapUserNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    except BootstrapUserInactiveError as error:
        print(f"error: {error}", file=sys.stderr)
        return 4
    except BootstrapEmailNotVerifiedError as error:
        print(f"error: {error}", file=sys.stderr)
        return 5
    except BootstrapOwnershipConflictError as error:
        print(f"error: {error}", file=sys.stderr)
        return 6
    except BootstrapInvalidArgumentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 7
    except BootstrapTenantError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(_safe_result_payload(result), indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
