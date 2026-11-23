#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 <base-env-file> <release-sha> <backend-image-repo> <frontend-image-repo>" >&2
  exit 2
fi

BASE_ENV="$1"
RELEASE_SHA="$2"
BACKEND_REPO="$3"
FRONTEND_REPO="$4"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
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

if [[ ! "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Release SHA must be a full 40-character lowercase git SHA" >&2
  exit 2
fi
if [[ ! -f "$BASE_ENV" ]]; then
  echo "Base environment file not found: $BASE_ENV" >&2
  exit 2
fi

STATE_DIR=".ops-state"
RELEASES_DIR="$STATE_DIR/releases"
DEPLOYMENTS_DIR="$STATE_DIR/deployments"
NEXT_ENV=".release.env.next"
CURRENT_ENV=".release.env"
PREVIOUS_ENV=".release.env.previous"
mkdir -p "$RELEASES_DIR" "$DEPLOYMENTS_DIR"
chmod 700 "$STATE_DIR" "$RELEASES_DIR" "$DEPLOYMENTS_DIR"

# Deploy and manual rollback mutate the same release pointers and services.
# Hold a shared advisory lock for the entire command, before reading or
# writing NEXT_ENV, CURRENT_ENV, the manifest or the recovery marker.
umask 077
exec {DEPLOY_LOCK_FD}>> "$STATE_DIR/deploy.lock"
if ! flock -n "$DEPLOY_LOCK_FD"; then
  echo "Deployment refused: another deploy or rollback is already running" >&2
  exit 2
fi

guard_legacy_g5_cutover

# A failed automatic rollback can leave partially migrated services. Never
# try another deployment until a human has reconciled the recovery marker.
RECOVERY_REQUIRED="$STATE_DIR/recovery-required"
if [[ -e "$RECOVERY_REQUIRED" || -L "$RECOVERY_REQUIRED" ]]; then
  echo "Deployment refused: unresolved recovery incident at $RECOVERY_REQUIRED" >&2
  exit 2
fi

# Never install EXIT cleanup against a caller-owned input file or symlink.
if [[ -L "$NEXT_ENV" || ( -e "$NEXT_ENV" && "$BASE_ENV" -ef "$NEXT_ENV" ) ]]; then
  echo "Deployment refused: base env aliases a temporary candidate or candidate is a symlink" >&2
  exit 2
fi

marker_tmp=""
backup_receipt=""
prepared_dir=""
cleanup() {
  trap - ERR
  set +e
  if [[ -n "$prepared_dir" ]]; then
    rm -rf -- "$prepared_dir"
  fi
  rm -f -- "$NEXT_ENV" "$marker_tmp" "$backup_receipt"
}
trap cleanup EXIT

cp "$BASE_ENV" "$NEXT_ENV"
{
  echo
  echo "# Immutable image refs injected by deploy_remote.sh"
  echo "BACKEND_IMAGE=${BACKEND_REPO}:${RELEASE_SHA}"
  echo "FRONTEND_IMAGE=${FRONTEND_REPO}:${RELEASE_SHA}"
} >> "$NEXT_ENV"
chmod 600 "$NEXT_ENV"
python3 ops/preflight.py "$NEXT_ENV"

eval "$(python3 - "$NEXT_ENV" <<'PY'
import shlex
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env
values = read_env(Path(sys.argv[1]))
for key in (
    'POSTGRES_USER', 'POSTGRES_DB', 'BACKUP_DIR', 'PUBLIC_BASE_URL',
    'LOAD_DURATION_SECONDS', 'LOAD_CONCURRENCY', 'LOAD_TARGET_RPS', 'MAX_P95_MS', 'MAX_ERROR_RATE'
):
    value = values.get(key, '')
    print(f'{key}={shlex.quote(value)}')
PY
)"

LOAD_DURATION_SECONDS="${LOAD_DURATION_SECONDS:-15}"
LOAD_CONCURRENCY="${LOAD_CONCURRENCY:-8}"
LOAD_TARGET_RPS="${LOAD_TARGET_RPS:-6}"
MAX_P95_MS="${MAX_P95_MS:-750}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-0.005}"

previous_release_sha=""
had_previous=0
if [[ -f "$CURRENT_ENV" ]]; then
  cp "$CURRENT_ENV" "$PREVIOUS_ENV"
  chmod 600 "$PREVIOUS_ENV"
  had_previous=1
  if [[ -f .release-sha ]]; then
    previous_release_sha="$(tr -d '[:space:]' < .release-sha)"
  fi
  if [[ "$previous_release_sha" =~ ^[0-9a-f]{40}$ ]]; then
    cp "$CURRENT_ENV" "$RELEASES_DIR/${previous_release_sha}.env"
    chmod 600 "$RELEASES_DIR/${previous_release_sha}.env"
  fi
fi
if [[ "$had_previous" -eq 1 && ! "$previous_release_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Deployment refused: existing release has no trustworthy .release-sha" >&2
  exit 2
fi

previous_public_base_url=""
if [[ "$had_previous" -eq 1 ]]; then
  python3 ops/preflight.py "$PREVIOUS_ENV"
  # A database switch requires a separately rehearsed migration and recovery
  # plan; the automatic rollback can only restore the same PostgreSQL identity.
  previous_public_base_url="$(python3 - "$PREVIOUS_ENV" "$NEXT_ENV" <<'PY'
import re
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env

previous = read_env(Path(sys.argv[1]))
next_release = read_env(Path(sys.argv[2]))
keys = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DB_URL", "COMPOSE_PROJECT_NAME")
# The two env files may interpolate the same raw expression differently from
# file-local definitions. Compare only literal connection identities to avoid
# backing up one PostgreSQL volume and restoring into another.
def compose_interpolates(path, key):
    # Match the last occurrence, as read_env does. Compose single quotes
    # disable interpolation; unquoted/double quoted values expand variables.
    raw_value = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            raw_value = value.strip()
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] == "'":
        return False
    # Compose treats $$ as a literal $, not as a variable reference.
    return bool(re.search(r"\$(?:\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*)", raw_value.replace("$$", "")))

for key in keys:
    for path in (Path(sys.argv[1]), Path(sys.argv[2])):
        if compose_interpolates(path, key):
            print(f"Deployment refused: {key} must not contain variable interpolation", file=sys.stderr)
            raise SystemExit(2)
# Compose interpolates ${VAR} from the external shell environment, so two
# identical raw dotenv values can still target distinct projects. Fail closed
# on nonliteral project names before probing/backup/restoring any database.
for value in (previous.get("COMPOSE_PROJECT_NAME", ""), next_release.get("COMPOSE_PROJECT_NAME", "")):
    if value and not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
        print("Deployment refused: COMPOSE_PROJECT_NAME must be a literal lowercase project name", file=sys.stderr)
        raise SystemExit(2)
if any(previous.get(key) != next_release.get(key) for key in keys):
    print("Deployment refused: PostgreSQL connection changed; manual migration required", file=sys.stderr)
    raise SystemExit(2)
print(previous["PUBLIC_BASE_URL"])
PY
)"
fi

# A populated preview may predate this deployment manager. An absent
# .release.env is NOT proof that the Docker project is a new/empty install:
# rewriting an unmanaged application provides no trustworthy rollback images.
# Refuse before touching active containers or moving release pointers.
if [[ "$had_previous" -eq 0 ]]; then
  refuse_unmanaged() {
    echo "Deployment refused: $1. Inspect and adopt the existing deployment with a separately rehearsed recovery plan." >&2
    exit 2
  }
  if [[ -e .release-sha || -L .release-sha || -e "$PREVIOUS_ENV" || -L "$PREVIOUS_ENV" ]]; then
    refuse_unmanaged "orphaned release metadata without $CURRENT_ENV"
  fi
  if [[ -n "$(find "$DEPLOYMENTS_DIR" -maxdepth 1 -type f -name '*.json' -print -quit)" ]]; then
    refuse_unmanaged "deployment manifests exist without $CURRENT_ENV"
  fi
  if [[ -n "$(find "$RELEASES_DIR" -maxdepth 1 -type f -name '*.env' -print -quit)" ]]; then
    refuse_unmanaged "archived releases exist without $CURRENT_ENV"
  fi
  if ! existing_containers="$(docker compose --env-file "$NEXT_ENV" -f "$COMPOSE_FILE" ps -a -q)"; then
    refuse_unmanaged "unable to inspect existing Docker Compose project"
  fi
  if [[ -n "${existing_containers//[[:space:]]/}" ]]; then
    refuse_unmanaged "unmanaged Docker Compose containers exist"
  fi
fi

# Persist the in-progress recovery guard BEFORE mutating the active release.
# A process crash, disk exhaustion or failure inside the ERR trap must not
# silently permit another deployment against an uncertain state.
marker_tmp="$(mktemp "$STATE_DIR/recovery-required.XXXXXXXX")"
printf 'failed_release=%s\nprevious_release=%s\nreason=deployment_in_progress\n' \
  "$RELEASE_SHA" "$previous_release_sha" > "$marker_tmp"
ln -T -- "$marker_tmp" "$RECOVERY_REQUIRED"
clear_recovery_marker() {
  if [[ -L "$RECOVERY_REQUIRED" || ! "$marker_tmp" -ef "$RECOVERY_REQUIRED" ]]; then
    echo "Recovery marker changed during deployment; operator inspection required" >&2
    return 2
  fi
  rm -f -- "$RECOVERY_REQUIRED"
}
rollback_backup=""
prepared_receipt=""
release_mutation_started=0
schema_integrity_uncertain=0
handle_deployment_error() {
  local exit_code=$?
  trap - ERR
  set +e
  echo "Deployment failed; entering fail-closed incident handling" >&2

  # Before release startup, no migrations or seed work has been requested.
  # NEVER call compose up for a pre-migration failure: dependency startup would
  # run migrate/seed even for a missing or untrusted database schema.
  if [[ "$release_mutation_started" -eq 0 ]]; then
    # For an existing release, the active env still points to the previous
    # release. Recovery at this stage needs no additional disk writes.
    if [[ "$had_previous" -eq 1 && "$schema_integrity_uncertain" -ne 1 ]]; then
      clear_recovery_marker
    fi
    if [[ -e "$RECOVERY_REQUIRED" || -L "$RECOVERY_REQUIRED" ]]; then
      echo "CRITICAL: deployment stopped before migrations; inspection required ($RECOVERY_REQUIRED)" >&2
    fi
    exit "$exit_code"
  fi

  # A live release may commit writes AFTER the snapshot was captured.
  # Restoring that old snapshot would silently erase those confirmed writes.
  # The legacy manager has no durable, universal writer barrier, so it may
  # NEVER auto-restore an earlier PostgreSQL dump after release mutation.
  echo "CRITICAL: database restore is NOT SAFE after release mutation without a certified G5 writer barrier" >&2
  echo "Stopping application writers and preserving the current database for operator recovery" >&2
  if ! docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" stop -t 120 backend worker migrate seed; then
    echo "CRITICAL: writer stop failed; check live containers and database sessions immediately" >&2
  fi
  echo "CRITICAL: recovery marker retained; no database restore or automatic reopening ($RECOVERY_REQUIRED)" >&2
  exit "$exit_code"
}
trap handle_deployment_error ERR

candidate_env="$NEXT_ENV"
database_env="$PREVIOUS_ENV"
if [[ "$had_previous" -eq 0 ]]; then
  mv -T -- "$NEXT_ENV" "$CURRENT_ENV"
  candidate_env="$CURRENT_ENV"
  database_env="$CURRENT_ENV"
fi

# Use the previous release identity for managed deployments. Starting only
# database cannot run migrate/seed, and recovers a stopped database safely.
echo "Ensuring PostgreSQL is healthy before backup"
docker compose --env-file "$database_env" -f "$COMPOSE_FILE" up -d --wait --wait-timeout 120 database

# Fail closed on a missing or failed database probe. A network or credential
# error must never be mistaken for an empty first-install database.
if ! has_schema="$(docker compose --env-file "$database_env" -f "$COMPOSE_FILE" exec -T database \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT to_regclass('public.users') IS NOT NULL;" 2>/dev/null)"; then
  schema_integrity_uncertain=1
  echo "Database schema probe failed; refusing deployment without a known backup state" >&2
  false
fi
case "$has_schema" in
  t)
    # A first-install candidate must never silently adopt an existing schema.
    # Without a previous immutable release, recovery could restore data but
    # cannot restore the application's former images/configuration.
    if [[ "$had_previous" -eq 0 ]]; then
      schema_integrity_uncertain=1
      echo "Existing users schema without managed release metadata; refusing first-install migration" >&2
      false
    fi
    backup_receipt="$(mktemp "$STATE_DIR/backup-receipt.XXXXXXXX")"
    BACKUP_RECEIPT_FILE="$backup_receipt" bash ops/backup_postgres.sh "$candidate_env"
    if [[ ! -s "$backup_receipt" ]]; then
      echo "Backup completed without an exact archive receipt" >&2
      false
    fi
    IFS= read -r candidate_backup < "$backup_receipt"
    rm -f -- "$backup_receipt"
    backup_receipt=""

    backup_basename="${candidate_backup##*/}"
    if [[ "$(realpath -m -- "$(dirname -- "$candidate_backup")")" != "$(realpath -m -- "$BACKUP_DIR")" ||
          ! "$backup_basename" =~ ^${POSTGRES_DB}-[0-9]{8}T[0-9]{6}Z-[[:alnum:]]{8}\.dump$ ||
          ! -s "$candidate_backup" || ! -s "${candidate_backup}.sha256" ||
          -L "$candidate_backup" ]]; then
      echo "Backup receipt did not identify a valid new archive in BACKUP_DIR" >&2
      false
    fi
    rollback_backup="$candidate_backup"

    # Allocate and verify the rollback copy while the old release is active.
    prepared_dir="$(mktemp -d "$STATE_DIR/restore.XXXXXXXX")"
    prepared_receipt="$(DEPLOY_LOCK_FD="$DEPLOY_LOCK_FD" RESTORE_PREPARE_ONLY=1 RESTORE_START_SERVICES=0 \
      bash ops/restore_postgres.sh "$PREVIOUS_ENV" "$rollback_backup" "PREPARE:${POSTGRES_DB}" "$prepared_dir")"
    if [[ ! "$prepared_receipt" =~ ^[0-9a-f]{64}:[0-9]+:[0-9]+$ ]]; then
      echo "Deployment refused: invalid prepared archive receipt" >&2
      false
    fi
    ;;
  f)
    if [[ "$had_previous" -eq 1 ]]; then
      schema_integrity_uncertain=1
      echo "Existing release has no users schema; refusing an unbacked first-install path" >&2
      false
    fi
    echo "No existing application schema; treating this as first deployment"
    ;;
  *)
    schema_integrity_uncertain=1
    echo "Unexpected schema probe result; refusing deployment without backup" >&2
    false
    ;;
esac

echo "Pulling immutable release images and pinned edge images"
docker compose --env-file "$candidate_env" -f "$COMPOSE_FILE" pull migrate seed backend worker frontend nginx caddy

echo "Applying migrations and starting release ${RELEASE_SHA}"
# Enter the guarded mutation phase BEFORE moving the release pointer. A failed
# or interrupted metadata publish cannot be mistaken for a pre-mutation error.
release_mutation_started=1
if [[ "$had_previous" -eq 1 ]]; then
  mv -T -- "$NEXT_ENV" "$CURRENT_ENV"
fi
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" up -d --remove-orphans

echo "Waiting for HTTPS edge and certificate readiness at ${PUBLIC_BASE_URL}"
edge_ready=0
for _ in $(seq 1 60); do
  if python3 - "$PUBLIC_BASE_URL" <<'PY' >/dev/null 2>&1
import sys
import urllib.request
base = sys.argv[1].rstrip('/')
with urllib.request.urlopen(base + '/health', timeout=3) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
  then
    edge_ready=1
    break
  fi
  sleep 2
done
if [[ "$edge_ready" -ne 1 ]]; then
  echo "HTTPS edge did not become ready within 120 seconds" >&2
  docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" ps >&2 || true
  docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" logs --tail=200 caddy nginx backend >&2 || true
  false  # Trigger ERR trap and controlled rollback after release mutation.
fi

echo "Running post-deploy smoke against ${PUBLIC_BASE_URL}"
python3 ops/smoke_http.py \
  --base-url "$PUBLIC_BASE_URL" \
  --requests 20 \
  --max-p95-ms "$MAX_P95_MS"

echo "Running bounded post-deploy load probe"
python3 ops/load_smoke.py \
  --base-url "$PUBLIC_BASE_URL" \
  --duration-seconds "$LOAD_DURATION_SECONDS" \
  --concurrency "$LOAD_CONCURRENCY" \
  --target-rps "$LOAD_TARGET_RPS" \
  --max-p95-ms "$MAX_P95_MS" \
  --max-error-rate "$MAX_ERROR_RATE"

# Preserve fail-closed incident handling during release metadata publication.
# A failed copy, manifest write, pointer update or marker removal after startup
# is still a post-mutation incident and must stop writers.
cp "$CURRENT_ENV" "$RELEASES_DIR/${RELEASE_SHA}.env"
chmod 600 "$RELEASES_DIR/${RELEASE_SHA}.env"
python3 - "$DEPLOYMENTS_DIR/${RELEASE_SHA}.json" "$RELEASE_SHA" "$previous_release_sha" "$rollback_backup" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
payload = {
    "release_sha": sys.argv[2],
    "previous_release_sha": sys.argv[3] or None,
    "rollback_backup": sys.argv[4] or None,
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
rm -f "$PREVIOUS_ENV"
echo "$RELEASE_SHA" > .release-sha
chmod 600 .release-sha
clear_recovery_marker
trap - ERR
echo "Deployment succeeded: ${RELEASE_SHA}"
