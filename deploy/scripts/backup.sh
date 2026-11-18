#!/usr/bin/env bash
# Daily pg_dump backup for VietRP Studio. Run by vietrp-backup.service as user vietrp.
#
# Writes /var/backups/vietrp/vietrp-YYYYmmdd-HHMMSS.dump (pg_dump custom format),
# checks that the archive is readable, then keeps only the newest $VIETRP_BACKUP_KEEP dumps.
# Logs file names and sizes only. Never prints connection details.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=pg_env.sh
source "$SCRIPT_DIR/pg_env.sh"

BACKUP_DIR="${VIETRP_BACKUP_DIR:-/var/backups/vietrp}"
# 14 daily dumps = two weeks of restore points. Owner decision; see deploy/README.md.
KEEP="${VIETRP_BACKUP_KEEP:-14}"
# Pinned to PostgreSQL 17 binaries: pg_dump must be at least as new as the server.
PG_DUMP="${VIETRP_PG_DUMP:-/usr/lib/postgresql/17/bin/pg_dump}"
PG_RESTORE="${VIETRP_PG_RESTORE:-/usr/lib/postgresql/17/bin/pg_restore}"

if ! [[ "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
  echo "VIETRP_BACKUP_KEEP must be a positive integer" >&2
  exit 1
fi

mkdir -p -- "$BACKUP_DIR"
load_pg_env

timestamp="$(date -u +%Y%m%d-%H%M%S)"
partial="$BACKUP_DIR/.vietrp-$timestamp.dump.partial"
final="$BACKUP_DIR/vietrp-$timestamp.dump"

# Remove the partial file if anything fails before the final rename.
trap 'rm -f -- "$partial"' EXIT

"$PG_DUMP" --format=custom --no-owner --no-privileges --file="$partial"
"$PG_RESTORE" --list "$partial" > /dev/null
mv -- "$partial" "$final"
echo "backup written: $final ($(stat -c %s -- "$final") bytes)"

# Rotation: newest first, drop everything after the first $KEEP files.
mapfile -t stale < <(ls -1t -- "$BACKUP_DIR"/vietrp-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))")
for file in "${stale[@]}"; do
  rm -f -- "$file"
  echo "rotated out: $file"
done
