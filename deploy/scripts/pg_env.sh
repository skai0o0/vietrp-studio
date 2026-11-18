# Sourced by backup.sh and restore.sh. Not executable on its own.
#
# Turns DATABASE_URL (SQLAlchemy form, postgresql+asyncpg://...) into libpq PG* variables.
# The password goes into PGPASSWORD, so it never appears in a process argument list.

load_pg_env() {
  local env_file="${VIETRP_ENV_FILE:-/etc/vietrp/vietrp.env}"

  # Under systemd, EnvironmentFile= already sets DATABASE_URL. For manual runs as root, read only
  # that one line. The file is never executed, so its other values are never interpreted.
  if [[ -z "${DATABASE_URL:-}" && -r "$env_file" ]]; then
    DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' "$env_file" | head -n 1)"
    export DATABASE_URL
  fi

  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is not set (expected in $env_file)" >&2
    return 1
  fi

  local py="${VIETRP_PYTHON:-/opt/vietrp/backend/.venv/bin/python}"
  local exports
  # -I isolates the interpreter (no cwd on sys.path, no PYTHON* env vars).
  exports="$("$py" -I -c '
import os
import shlex
from urllib.parse import unquote, urlsplit

url = urlsplit(os.environ["DATABASE_URL"])
if not url.scheme.startswith("postgresql"):
    raise SystemExit("DATABASE_URL must start with postgresql")
values = {
    "PGHOST": url.hostname or "127.0.0.1",
    "PGPORT": str(url.port or 5432),
    "PGDATABASE": unquote(url.path.lstrip("/")),
    "PGUSER": unquote(url.username or ""),
    "PGPASSWORD": unquote(url.password or ""),
}
for key, value in values.items():
    print(f"export {key}={shlex.quote(value)}")
')"
  eval "$exports"
}
