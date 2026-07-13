#!/usr/bin/env bash
# Generate a pg_restore command for CloserOS PostgreSQL restores.
# This wrapper never executes pg_restore unless --execute is passed explicitly.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: restore_pg.sh --input PATH [--database-url URL] [--execute]

Generates (and optionally runs) a pg_restore into an empty or pre-cleared database.

Safety rules:
  - Requires --confirm-destructive when targeting non-local hosts.
  - Refuses known local/CI credential markers unless --allow-unsafe is set.
  - Default mode prints the command only.
  - Never prints the full database URL.

Environment:
  DATABASE_URL   PostgreSQL connection URI (overridden by --database-url)
EOF
}

DATABASE_URL="${DATABASE_URL:-}"
INPUT=""
EXECUTE=0
ALLOW_UNSAFE=0
CONFIRM_DESTRUCTIVE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database-url)
      DATABASE_URL="${2:-}"
      shift 2
      ;;
    --input)
      INPUT="${2:-}"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --allow-unsafe)
      ALLOW_UNSAFE=1
      shift
      ;;
    --confirm-destructive)
      CONFIRM_DESTRUCTIVE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$DATABASE_URL" ]]; then
  echo "error: DATABASE_URL is not set" >&2
  exit 2
fi

if [[ -z "$INPUT" ]]; then
  echo "error: --input is required" >&2
  exit 2
fi

if [[ ! -f "$INPUT" ]]; then
  echo "error: backup file not found: $INPUT" >&2
  exit 2
fi

if [[ "$ALLOW_UNSAFE" -eq 0 ]]; then
  if [[ "$DATABASE_URL" == *"closeros_local_only_change_me"* ]] \
    || [[ "$DATABASE_URL" == *"closeros_ci_only_not_production"* ]]; then
    echo "error: refusing restore with known non-production credential marker" >&2
    exit 2
  fi
fi

HOST="$(python3 - <<'PY' "$DATABASE_URL"
import sys
from urllib.parse import urlparse
print((urlparse(sys.argv[1]).hostname or "").lower())
PY
)"

if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && "$HOST" != "::1" ]]; then
  if [[ "$CONFIRM_DESTRUCTIVE" -eq 0 ]]; then
    echo "error: non-local restore requires --confirm-destructive" >&2
    exit 2
  fi
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "error: pg_restore is not installed or not on PATH" >&2
  exit 1
fi

CMD=(
  pg_restore
  --clean
  --if-exists
  --no-owner
  --no-acl
  --dbname="$DATABASE_URL"
  "$INPUT"
)

echo "target host: ${HOST:-unknown}"
echo "input file: ${INPUT}"
printf 'generated command: pg_restore --clean --if-exists --no-owner --no-acl --dbname=<DATABASE_URL> %q\n' "$INPUT"

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "dry-run: re-run with --execute to perform the restore"
  exit 0
fi

echo "executing pg_restore..."
"${CMD[@]}"
echo "restore complete"
