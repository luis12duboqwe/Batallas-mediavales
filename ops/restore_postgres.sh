#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"
BACKUP_FILE="${2:-}"
CONFIRMATION="${3:-}"
PREPARED_DIR="${4:-}"
PREPARED_RECEIPT="${5:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
RESTORE_START_SERVICES="${RESTORE_START_SERVICES:-1}"
RESTORE_PREPARE_ONLY="${RESTORE_PREPARE_ONLY:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# G5 cutover state is authoritative. No legacy entrypoint understands
# the verified backup FD or durable writer barrier. Check once on entry
# and again after obtaining the shared release lock to close the entry race.
guard_legacy_g5_cutover() {
  if [[ -L .ops-state || ( -e .ops-state && ! -d .ops-state ) ]]; then
    echo "Legacy G5 operation refused: unsafe .ops-state directory" >&2
    exit 2
  fi
  local g5_state
  for g5_state in .ops-state/g5-cutover.json .ops-state/g5-cutover-activated; do
    if [[ -e "$g5_state" || -L "$g5_state" ]]; then
      echo "Legacy G5 operation refused: cutover state exists ($g5_state); certified coordinator required" >&2
      exit 2
    fi
  done
}
guard_legacy_g5_cutover

if [[ -z "$BACKUP_FILE" || $# -gt 5 ]]; then
  echo "Usage: $0 <env-file> <backup.dump> RESTORE:<database>" >&2
  exit 2
fi
if [[ "$RESTORE_START_SERVICES" != "0" && "$RESTORE_START_SERVICES" != "1" ]]; then
  echo "RESTORE_START_SERVICES must be 0 or 1" >&2
  exit 2
fi
if [[ "$RESTORE_PREPARE_ONLY" != "0" && "$RESTORE_PREPARE_ONLY" != "1" ]]; then
  echo "RESTORE_PREPARE_ONLY must be 0 or 1" >&2
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
   [[ "/proc/$$/fd/$DEPLOY_LOCK_FD" -ef "$DEPLOY_LOCK_FILE" ]]; then
  exec {RESTORE_PROBE_FD}>> "$DEPLOY_LOCK_FILE"
  if flock -n "$RESTORE_PROBE_FD"; then
    RESTORE_LOCK_FD="$RESTORE_PROBE_FD"
  else
    exec {RESTORE_PROBE_FD}>&-
    if flock -n "$DEPLOY_LOCK_FD"; then
      NESTED_RESTORE=1
    else
      echo "Restore refused: another deploy, rollback or restore is already running" >&2
      exit 2
    fi
  fi
else
  umask 077
  exec {RESTORE_LOCK_FD}>> "$DEPLOY_LOCK_FILE"
  if ! flock -n "$RESTORE_LOCK_FD"; then
    echo "Restore refused: another deploy, rollback or restore is already running" >&2
    exit 2
  fi
fi

guard_legacy_g5_cutover

RECOVERY_REQUIRED="$STATE_DIR/recovery-required"
validate_recovery_marker() {
  if [[ -e "$RECOVERY_REQUIRED" || -L "$RECOVERY_REQUIRED" ]]; then
    if [[ -L "$RECOVERY_REQUIRED" || ! -f "$RECOVERY_REQUIRED" ||
          ! -O "$RECOVERY_REQUIRED" || ! -s "$RECOVERY_REQUIRED" ]]; then
      echo "Restore refused: invalid recovery marker at $RECOVERY_REQUIRED" >&2
      return 2
    fi
  fi
}
validate_recovery_marker

# When an aborted operation could not publish the canonical incident marker,
# its surviving recovery-required.* evidence must still forbid restore.
if [[ ! -e "$RECOVERY_REQUIRED" && ! -L "$RECOVERY_REQUIRED" ]]; then
  if ! orphaned_recovery="$(find "$STATE_DIR" -maxdepth 1 -name 'recovery-required.*' -print -quit)"; then
    echo "Restore refused: cannot inspect orphaned recovery evidence" >&2
    exit 2
  fi
  if [[ -n "$orphaned_recovery" ]]; then
    echo "Restore refused: orphaned recovery evidence requires certified G5 coordinator ($orphaned_recovery)" >&2
    exit 2
  fi
fi

# A direct legacy restore during an unresolved incident, or with an active
# managed release, can discard commits made after the archive was captured.
# No durable G5 write barrier authorizes that destructive operation yet.
# PREPARE_ONLY is read-only; nested restore is owned by the caller's deploy
# lock and remains a separately tracked G5 risk until the coordinator lands.
if [[ "$RESTORE_PREPARE_ONLY" == 0 && "$NESTED_RESTORE" == 0 ]]; then
  if [[ -e "$RECOVERY_REQUIRED" || -L "$RECOVERY_REQUIRED" ]]; then
    echo "Restore refused: unresolved recovery incident requires certified G5 coordinator" >&2
    exit 2
  fi
  if [[ -e .release-sha || -L .release-sha ||
        -e .release.env || -L .release.env ]]; then
    echo "Restore refused: managed release requires certified G5 writer barrier" >&2
    exit 2
  fi
fi

RESTORE_TMP_DIR=""
RESTORE_MARKER_TMP=""
cleanup_restore() {
  if [[ -n "$RESTORE_TMP_DIR" ]]; then
    rm -rf -- "$RESTORE_TMP_DIR"
  fi
  rm -f -- "$RESTORE_MARKER_TMP"
}
trap cleanup_restore EXIT

if [[ "$RESTORE_PREPARE_ONLY" == 1 ]]; then
  python3 ops/preflight.py "$ENV_FILE" >&2
else
  python3 ops/preflight.py "$ENV_FILE"
fi
ENV_VALUES="$(python3 - "$ENV_FILE" <<'PYENV'
import shlex
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env
values = read_env(Path(sys.argv[1]))
for key in ('POSTGRES_USER', 'POSTGRES_DB'):
    print(f'{key}={shlex.quote(values[key])}')
PYENV
)"
eval "$ENV_VALUES"

if [[ "$RESTORE_PREPARE_ONLY" == 1 ]]; then
  if [[ "$CONFIRMATION" != "PREPARE:${POSTGRES_DB}" || "$RESTORE_START_SERVICES" != 0 ||
        -z "$PREPARED_DIR" || -n "$PREPARED_RECEIPT" ]]; then
    echo "Preparation requires PREPARE:${POSTGRES_DB}, a private rollback directory and RESTORE_START_SERVICES=0" >&2
    exit 2
  fi
elif [[ "$CONFIRMATION" != "RESTORE:${POSTGRES_DB}" ]]; then
  echo "Restore refused. Re-run with confirmation: RESTORE:${POSTGRES_DB}" >&2
  exit 2
fi

umask 077
EXPECTED_ID=""
if [[ -n "$PREPARED_DIR" ]]; then
  if [[ "$NESTED_RESTORE" != 1 || ! "$PREPARED_DIR" =~ ^\.ops-state/restore\.[[:alnum:]]{8}$ ||
        -L "$PREPARED_DIR" || ! -d "$PREPARED_DIR" || ! -O "$PREPARED_DIR" ||
        "$(stat -c %a -- "$PREPARED_DIR")" != 700 ]]; then
    echo "Restore refused: invalid private rollback directory or missing parent lock" >&2
    exit 2
  fi
  RESTORE_SNAPSHOT="$PREPARED_DIR/archive.dump"
else
  if [[ -n "$PREPARED_RECEIPT" ]]; then
    echo "Restore refused: prepared receipt requires a private rollback directory" >&2
    exit 2
  fi
  RESTORE_TMP_DIR="$(mktemp -d "$STATE_DIR/restore.XXXXXXXX")"
  RESTORE_SNAPSHOT="$RESTORE_TMP_DIR/archive.dump"
fi

if [[ "$RESTORE_PREPARE_ONLY" == 0 && -n "$PREPARED_DIR" ]]; then
  if [[ "$BACKUP_FILE" != "$RESTORE_SNAPSHOT" ||
        ! "$PREPARED_RECEIPT" =~ ^([0-9a-f]{64}):([0-9]+:[0-9]+)$ ]]; then
    echo "Restore refused: invalid prepared archive path or receipt" >&2
    exit 2
  fi
  EXPECTED_HASH="${BASH_REMATCH[1]}"
  EXPECTED_ID="${BASH_REMATCH[2]}"
else
  if [[ ! -s "$BACKUP_FILE" ]]; then
    echo "Restore refused: backup is missing or empty: $BACKUP_FILE" >&2
    exit 2
  fi
  CHECKSUM_FILE="${BACKUP_FILE}.sha256"
  if [[ ! -f "$CHECKSUM_FILE" ]]; then
    echo "Restore refused: checksum file missing: $CHECKSUM_FILE" >&2
    exit 2
  fi
  # The checksum filename field is informational. Hash the selected bytes.
  EXPECTED_HASH="$(awk 'NR == 1 {print $1}' "$CHECKSUM_FILE")"
  if [[ ! "$EXPECTED_HASH" =~ ^[[:xdigit:]]{64}$ ]] || [[ "$(wc -l < "$CHECKSUM_FILE")" -ne 1 ]]; then
    echo "Restore refused: invalid backup checksum format" >&2
    exit 2
  fi
  # The rollback parent owns its directory and cleans up even a partial copy.
  (set -o noclobber; cat -- "$BACKUP_FILE" > "$RESTORE_SNAPSHOT")
  chmod 400 "$RESTORE_SNAPSHOT"
fi

if [[ -L "$RESTORE_SNAPSHOT" || ! -f "$RESTORE_SNAPSHOT" || ! -s "$RESTORE_SNAPSHOT" ||
      ! -O "$RESTORE_SNAPSHOT" || "$(stat -c '%a:%h' -- "$RESTORE_SNAPSHOT")" != 400:1 ]]; then
  echo "Restore refused: invalid private archive" >&2
  exit 2
fi
# Pin the inode for checksum, identity inspection and restore. Opening via
# procfs gives each reader its own offset, even after a pathname replacement.
exec {SNAPSHOT_FD}< "$RESTORE_SNAPSHOT"
SNAPSHOT_INPUT="/proc/$$/fd/$SNAPSHOT_FD"
SNAPSHOT_ID="$(stat -Lc '%d:%i' -- "$SNAPSHOT_INPUT")"
SNAPSHOT_CTIME="$(stat -Lc %z -- "$SNAPSHOT_INPUT")"
SNAPSHOT_HASH="$(sha256sum < "$SNAPSHOT_INPUT" | cut -d' ' -f1)"
if [[ "$SNAPSHOT_HASH" != "${EXPECTED_HASH,,}" || "$SNAPSHOT_ID" != "${EXPECTED_ID:-$SNAPSHOT_ID}" ]]; then
  echo "Restore refused: archive checksum mismatch or prepared archive replaced" >&2
  exit 2
fi
if [[ "$RESTORE_PREPARE_ONLY" == 1 ]]; then
  echo "Backup checksum verified for requested archive" >&2
else
  echo "Backup checksum verified for requested archive"
fi

# pg_restore --create uses the database name embedded in the archive.
ARCHIVE_DATABASE="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_restore --list < "$SNAPSHOT_INPUT" | sed -n 's/^;[[:space:]]*dbname: //p')"
if [[ "$ARCHIVE_DATABASE" != "$POSTGRES_DB" ]]; then
  echo "Restore refused: backup database '${ARCHIVE_DATABASE:-unknown}' does not match configured '${POSTGRES_DB}'" >&2
  exit 2
fi

if [[ -L "$RESTORE_SNAPSHOT" || ! "$RESTORE_SNAPSHOT" -ef "$SNAPSHOT_INPUT" ||
      "$SNAPSHOT_CTIME" != "$(stat -Lc %z -- "$SNAPSHOT_INPUT")" ]]; then
  echo "Restore refused: private archive changed during validation" >&2
  exit 2
fi

if [[ "$RESTORE_PREPARE_ONLY" == 1 ]]; then
  printf '%s:%s\n' "$SNAPSHOT_HASH" "$SNAPSHOT_ID"
  exit 0
fi

# A lock descriptor alone does not prove that a parent published a marker.
# Publish our own when absent, and retain it for operator certification.
validate_recovery_marker
if [[ ! -e "$RECOVERY_REQUIRED" && ! -L "$RECOVERY_REQUIRED" ]]; then
  RESTORE_MARKER_TMP="$(mktemp "$STATE_DIR/recovery-required.XXXXXXXX")"
  printf 'reason=standalone_restore_requires_operator_certification\n' > "$RESTORE_MARKER_TMP"
  ln -T -- "$RESTORE_MARKER_TMP" "$RECOVERY_REQUIRED"
fi
validate_recovery_marker
if [[ ! -f "$RECOVERY_REQUIRED" ]]; then
  echo "Restore refused: recovery marker disappeared" >&2
  exit 2
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
  -U "$POSTGRES_USER" -d postgres < "$SNAPSHOT_INPUT"

if [[ "$RESTORE_START_SERVICES" == "1" ]]; then
  echo "Starting selected release, migration chain and HTTPS edge"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx caddy
  echo "Restore completed. Run ops/smoke_http.py against PUBLIC_BASE_URL before ending maintenance."
else
  echo "Database-only restore verification completed; application services remain stopped."
fi
