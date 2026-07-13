#!/usr/bin/env python3
"""Report Alembic migration status without mutating the database schema."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros.infrastructure.alembic_config import build_alembic_config  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show Alembic migration status")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "").strip(),
        help="PostgreSQL URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary",
    )
    return parser.parse_args()


def _head_revisions(config: Config) -> list[str]:
    script = ScriptDirectory.from_config(config)
    return list(script.get_heads())


def _current_revision(database_url: str, config: Config) -> str | None:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current = context.get_current_revision()
        if current is not None:
            return current
        row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        return row[0] if row else None


def main() -> int:
    args = _parse_args()
    if not args.database_url:
        print("error: DATABASE_URL is not set and --database-url was not provided", file=sys.stderr)
        return 2

    if "closeros_local_only_change_me" in args.database_url:
        print(
            "warning: database URL appears to use committed local-development credentials",
            file=sys.stderr,
        )

    config = build_alembic_config(args.database_url)
    heads = _head_revisions(config)
    try:
        current = _current_revision(args.database_url, config)
    except Exception as error:  # noqa: BLE001 — surface connection errors to operators
        print(f"error: unable to read migration state: {error}", file=sys.stderr)
        return 1

    pending = current not in heads
    summary = {
        "current_revision": current,
        "head_revisions": heads,
        "pending_upgrade": pending,
    }

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"current revision: {current or '<none>'}")
        print(f"head revision(s): {', '.join(heads)}")
        print(f"pending upgrade: {'yes' if pending else 'no'}")

    return 1 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
