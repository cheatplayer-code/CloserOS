#!/usr/bin/env python3
"""Upgrade Alembic migrations with staging/production safety checks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros.infrastructure.alembic_config import build_alembic_config  # noqa: E402

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UNSAFE_PASSWORD_MARKERS = (
    "closeros_local_only_change_me",
    "closeros_ci_only_not_production",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upgrade database schema to Alembic head")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "").strip(),
        help="PostgreSQL URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--target",
        default="head",
        help="Alembic revision target (default: head)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-local hosts; acknowledges intentional schema change",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate safety checks and print the command without executing",
    )
    return parser.parse_args()


def _validate_database_url(database_url: str, *, confirm: bool) -> list[str]:
    issues: list[str] = []
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()

    if not database_url:
        issues.append("DATABASE_URL is empty")
        return issues

    if any(marker in database_url for marker in _UNSAFE_PASSWORD_MARKERS):
        issues.append("database URL contains known non-production credential marker")

    if host not in _LOCAL_HOSTS and not confirm:
        issues.append(
            "non-local database host requires --confirm (refusing accidental production upgrade)"
        )

    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        issues.append(f"unsupported database scheme: {parsed.scheme or '<missing>'}")

    return issues


def main() -> int:
    args = _parse_args()
    issues = _validate_database_url(args.database_url, confirm=args.confirm)
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 2

    config = build_alembic_config(args.database_url)
    command_line = (
        f"alembic upgrade {args.target} (database host: {urlparse(args.database_url).hostname})"
    )

    if args.dry_run:
        print(f"dry-run: would execute {command_line}")
        return 0

    print(f"executing {command_line}")
    command.upgrade(config, args.target)
    print("upgrade complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
