#!/usr/bin/env bash
# Generate a pg_dump command for CloserOS PostgreSQL backups.
# This wrapper never executes pg_dump unless --execute is passed explicitly.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: backup_pg.sh [--database-url URL] [--output PATH] [--execute]

Generates (and optionally runs) a logical pg_dump for CloserOS PostgreSQL.

Safety rules:
  - Refuses known local/CI credential markers unless --allow-unsafe is set.
  - Requires --execute to run pg_dump; default mode prints the command only.
  - Never prints the full database URL (host and database name only).

Environment:
  DATABASE_URL   PostgreSQL connection URI (overridden by --database-url)
EOF
}

DATABASE_URL="${DATABASE_URL:-}"
OUTPUT=""
EXECUTE=0
ALLOW_UNSAFE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database-url)
      DATABASE_URL="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
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

if [[ "$ALLOW_UNSAFE" -eq 0 ]]; then
  if [[ "$DATABASE_URL" == *"closeros_local_only_change_me"* ]] \
    || [[ "$DATABASE_URL" == *"closeros_ci_only_not_production"* ]]; then
    echo "error: refusing backup with known non-production credential marker" >&2
    echo "hint: pass --allow-unsafe only for intentional local/CI backups" >&2
    exit 2
  fi
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "error: pg_dump is not installed or not on PATH" >&2
  exit 1
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUTPUT" ]]; then
  OUTPUT="closeros-backup-${TIMESTAMP}.dump"
fi

# Parse host and database for operator visibility without leaking credentials.
HOST="$(python3 - <<'PY' "$DATABASE_URL"
import sys
from urllib.parse import urlparse
parsed = urlparse(sys.argv[1])
print(parsed.hostname or "unknown")
PY
)"
DB_NAME="$(python3 - <<'PY' "$DATABASE_URL"
import sys
from urllib.parse import urlparse
parsed = urlparse(sys.argv[1])
print((parsed.path or "/postgres").lstrip("/") or "postgres")
PY
)"

CMD=(
  pg_dump
  --format=custom
  --no-owner
  --no-acl
  --file="$OUTPUT"
  "$DATABASE_URL"
)

echo "target host: ${HOST}"
echo "target database: ${DB_NAME}"
echo "output file: ${OUTPUT}"
printf 'generated command: pg_dump --format=custom --no-owner --no-acl --file=%q <DATABASE_URL>\n' "$OUTPUT"

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "dry-run: re-run with --execute to perform the backup"
  exit 0
fi

echo "executing pg_dump..."
"${CMD[@]}"
echo "backup complete: ${OUTPUT}"
