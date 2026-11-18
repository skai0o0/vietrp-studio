#!/usr/bin/env bash
# Restores a VietRP pg_dump file into the live database. DESTRUCTIVE: replaces the current data.
#
# Usage (as root, API stopped first):
#   sudo systemctl stop vietrp-api
#   sudo env VIETRP_CONFIRM_RESTORE=yes bash /opt/vietrp/deploy/scripts/restore.sh <dump file>
#   sudo systemctl start vietrp-api
#
# Takes a safety dump of the current data first, then restores in one transaction.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=pg_env.sh
source "$SCRIPT_DIR/pg_env.sh"

dump="${1:-}"
if [[ -z "$dump" ]]; then
  echo "usage: restore.sh <dump file>" >&2
  exit 1
fi
if [[ ! -f "$dump" ]]; then
  echo "dump file not found: $dump" >&2
  exit 1
fi
if [[ "${VIETRP_CONFIRM_RESTORE:-}" != "yes" ]]; then
  echo "refusing to restore: set VIETRP_CONFIRM_RESTORE=yes to confirm" >&2
  exit 1
fi
if systemctl is-active --quiet vietrp-api.service; then
  echo "stop vietrp-api.service before restoring" >&2
  exit 1
fi

PG_RESTORE="${VIETRP_PG_RESTORE:-/usr/lib/postgresql/17/bin/pg_restore}"

echo "taking safety backup of current data first"
bash "$SCRIPT_DIR/backup.sh"

load_pg_env
"$PG_RESTORE" --clean --if-exists --no-owner --no-privileges --single-transaction --exit-on-error \
  --dbname="$PGDATABASE" "$dump"
echo "restore finished from: $dump"
