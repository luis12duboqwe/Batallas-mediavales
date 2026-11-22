#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"
BACKUP_FILE="${2:-}"
CONFIRMATION="${3:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
RESTORE_START_SERVICES="${RESTORE_START_SERVICES:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <env-file> <backup.dump> RESTORE:<database>" >&2
  exit 2
fi
if [[ "$RESTORE_START_SERVICES" != "0" && "$RESTORE_START_SERVICES" != "1" ]]; then
  echo "RESTORE_START_SERVICES must be 0 or 1" >&2
  exit 2
fi

STATE_DIR=".ops-state"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
DEPLOY_LOCK_FILE="$STATE_DIR/deploy.lock"
NESTED_RESTORE=0

# Standalone restores must serialize with deploys and rollbacks. Those callers
# pass their already-held descriptor so this nested operation shares the lock.
if [[ "${DEPLOY_LOCK_FD:-}" =~ ^[0-9]+$ ]] &&
   [[ -e "/proc/$$/fd/$DEPLOY_LOCK_FD" ]] &&
   [[ "/proc/$$/fd/$DEPLOY_LOCK_FD" -ef "$DEPLOY_LOCK_FILE" ]] &&
   flock -n "$DEPLOY_LOCK_FD"; then
  NESTED_RESTORE=1
else
  umask 077
  exec {RESTORE_LOCK_FD}>> "$DEPLOY_LOCK_FILE"
  if ! flock -n "$RESTORE_LOCK_FD"; then
    echo "Restore refused: another deploy, rollback or restore is already running" >&2
    exit 2
  fi
fi

python3 ops/preflight.py "$ENV_FILE"

eval "$(python3 - "$ENV_FILE" <<'PY'
import shlex
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env
values = read_env(Path(sys.argv[1]))
for key in ('POSTGRES_USER', 'POSTGRES_DB'):
    print(f'{key}={shlex.quote(values[key])}')
PY
)"

if [[ "$CONFIRMATION" != "RESTORE:${POSTGRES_DB}" ]]; then
  echo "Restore refused. Re-run with confirmation: RESTORE:${POSTGRES_DB}" >&2
  exit 2
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "Restore refused: backup is missing or empty: $BACKUP_FILE" >&2
  exit 2
fi

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ ! -f "$CHECKSUM_FILE" ]]; then
  echo "Restore refused: checksum file missing: $CHECKSUM_FILE" >&2
  exit 2
fi
# Verify the *selected* archive, not a different filename embedded in .sha256.
EXPECTED_HASH="$(awk 'NR == 1 {print $1}' "$CHECKSUM_FILE")"
if [[ ! "$EXPECTED_HASH" =~ ^[[:xdigit:]]{64}$ ]] || [[ "$(wc -l < "$CHECKSUM_FILE")" -ne 1 ]]; then
  echo "Restore refused: invalid backup checksum format" >&2
  exit 2
fi
ACTUAL_HASH="$(sha256sum "$BACKUP_FILE" | cut -d' ' -f1)"
if [[ "${EXPECTED_HASH,,}" != "$ACTUAL_HASH" ]]; then
  echo "Restore refused: checksum mismatch for requested archive" >&2
  exit 2
fi
echo "Backup checksum verified for requested archive"

# pg_restore --create uses the database name embedded in the archive, NOT the
# -d connection database. Refuse a wrong-database archive *before* stopping
# writers or terminating PostgreSQL sessions.
ARCHIVE_DATABASE="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_restore --list < "$BACKUP_FILE" | sed -n 's/^;[[:space:]]*dbname: //p')"
if [[ "$ARCHIVE_DATABASE" != "$POSTGRES_DB" ]]; then
  echo "Restore refused: backup database '${ARCHIVE_DATABASE:-unknown}' does not match configured '${POSTGRES_DB}'" >&2
  exit 2
fi

if [[ "$NESTED_RESTORE" -eq 0 ]]; then
  # A standalone restore can partially mutate PostgreSQL before failing. Keep
  # deployment blocked until an operator verifies recovery and clears the marker.
  RECOVERY_REQUIRED="$STATE_DIR/recovery-required"
  if [[ ! -e "$RECOVERY_REQUIRED" && ! -L "$RECOVERY_REQUIRED" ]]; then
    RESTORE_MARKER_TMP="$(mktemp "$STATE_DIR/recovery-required.XXXXXXXX")"
    printf 'reason=standalone_restore_requires_operator_certification\n' > "$RESTORE_MARKER_TMP"
    chmod 600 "$RESTORE_MARKER_TMP"
    mv -f -- "$RESTORE_MARKER_TMP" "$RECOVERY_REQUIRED"
  fi
fi

echo "Stopping application writers before restore"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop backend worker

echo "Terminating remaining database client sessions"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();"

echo "Restoring $BACKUP_FILE into $POSTGRES_DB"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_restore --clean --if-exists --create --no-owner --no-privileges --exit-on-error \
  -U "$POSTGRES_USER" -d postgres < "$BACKUP_FILE"

if [[ "$RESTORE_START_SERVICES" == "1" ]]; then
  echo "Starting selected release, migration chain and HTTPS edge"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx caddy
  echo "Restore completed. Run ops/smoke_http.py against PUBLIC_BASE_URL before ending maintenance."
else
  echo "Database-only restore verification completed; application services remain stopped."
fi
