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

# A failed automatic rollback can leave partially migrated services. Never
# try another deployment until a human has reconciled the recovery marker.
RECOVERY_REQUIRED="$STATE_DIR/recovery-required"
if [[ -e "$RECOVERY_REQUIRED" ]]; then
  echo "Deployment refused: unresolved recovery incident at $RECOVERY_REQUIRED" >&2
  exit 2
fi

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
    'LOAD_DURATION_SECONDS', 'LOAD_CONCURRENCY', 'MAX_P95_MS', 'MAX_ERROR_RATE'
):
    value = values.get(key, '')
    print(f'{key}={shlex.quote(value)}')
PY
)"

LOAD_DURATION_SECONDS="${LOAD_DURATION_SECONDS:-15}"
LOAD_CONCURRENCY="${LOAD_CONCURRENCY:-8}"
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
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env

previous = read_env(Path(sys.argv[1]))
next_release = read_env(Path(sys.argv[2]))
keys = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DB_URL")
if any(previous.get(key) != next_release.get(key) for key in keys):
    print("Deployment refused: PostgreSQL connection changed; manual migration required", file=sys.stderr)
    raise SystemExit(2)
print(previous["PUBLIC_BASE_URL"])
PY
)"
fi

# Persist the in-progress recovery guard BEFORE mutating the active release.
# A process crash, disk exhaustion or failure inside the ERR trap must not
# silently permit another deployment against an uncertain state.
printf 'failed_release=%s\nprevious_release=%s\nreason=deployment_in_progress\n' \
  "$RELEASE_SHA" "$previous_release_sha" > "$RECOVERY_REQUIRED"
chmod 600 "$RECOVERY_REQUIRED"
mv "$NEXT_ENV" "$CURRENT_ENV"

rollback_backup=""
backup_receipt=""
release_mutation_started=0
schema_integrity_uncertain=0
rollback() {
  local exit_code=$?
  trap - ERR
  set +e
  local recovered=0
  local recovery_env=""

  # The incident marker was written BEFORE the candidate env was activated.
  # Never erase it on failures, even when mktemp/cp/chmod/mv also fail.
  echo "Deployment failed; attempting controlled rollback" >&2

  # Before release startup, no migrations or seed work has been requested.
  # NEVER call compose up for a pre-migration failure: dependency startup would
  # run migrate/seed even for a missing or untrusted database schema.
  if [[ "$release_mutation_started" -eq 0 ]]; then
    if [[ "$had_previous" -eq 1 ]]; then
      recovery_env="$(mktemp ./.release.env.recovery.XXXXXXXX)"
      if [[ -n "$recovery_env" && -f "$recovery_env" ]] &&
         cp "$PREVIOUS_ENV" "$recovery_env" &&
         chmod 600 "$recovery_env" &&
         mv -f -- "$recovery_env" "$CURRENT_ENV"; then
        recovery_env=""
        if [[ "$schema_integrity_uncertain" -ne 1 ]]; then
          rm -f -- "$RECOVERY_REQUIRED"
        fi
      fi
    fi
    if [[ -e "$RECOVERY_REQUIRED" ]]; then
      echo "CRITICAL: deployment stopped before migrations; inspection required ($RECOVERY_REQUIRED)" >&2
    fi
    if [[ -n "$recovery_env" ]]; then rm -f -- "$recovery_env"; fi
    if [[ -n "$backup_receipt" ]]; then rm -f -- "$backup_receipt"; fi
    exit "$exit_code"
  fi

  if [[ "$had_previous" -eq 1 ]]; then
    recovery_env="$(mktemp ./.release.env.recovery.XXXXXXXX)"
    if [[ -n "$recovery_env" && -f "$recovery_env" ]] &&
       cp "$PREVIOUS_ENV" "$recovery_env" &&
       chmod 600 "$recovery_env"; then
      if [[ -n "$rollback_backup" && -f "$rollback_backup" ]]; then
        echo "Restoring pre-deploy database snapshot and previous application release" >&2
        if bash ops/restore_postgres.sh "$recovery_env" "$rollback_backup" "RESTORE:${POSTGRES_DB}"; then
          recovered=1
        fi
      elif [[ -z "$rollback_backup" ]]; then
        echo "No database snapshot was created; restoring previous application images only" >&2
        if docker compose --env-file "$recovery_env" -f "$COMPOSE_FILE" pull backend worker frontend &&
           docker compose --env-file "$recovery_env" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx caddy; then
          recovered=1
        fi
      fi
    fi

    if [[ "$recovered" -eq 1 ]]; then
      if python3 ops/smoke_http.py --base-url "$previous_public_base_url" --requests 20 --max-p95-ms "$MAX_P95_MS" &&
         mv -f -- "$recovery_env" "$CURRENT_ENV"; then
        recovered=2
        recovery_env=""
      fi
    fi
  else
    echo "No previous release exists; cannot automatically restore this deployment" >&2
  fi

  if [[ "$recovered" -eq 2 ]]; then
    # .release-sha already points to the previous release during a failed
    # deployment. Preserve it; only the active env needed to be restored.
    rm -f -- "$RECOVERY_REQUIRED"
  else
    printf 'failed_release=%s\nprevious_release=%s\nreason=automatic_rollback_failed\n' \
      "$RELEASE_SHA" "$previous_release_sha" > "$RECOVERY_REQUIRED" || true
    chmod 600 "$RECOVERY_REQUIRED" || true
    echo "CRITICAL: rollback not verified; manual recovery required ($RECOVERY_REQUIRED)" >&2
  fi
  if [[ -n "$recovery_env" ]]; then rm -f -- "$recovery_env"; fi
  if [[ -n "$backup_receipt" ]]; then rm -f -- "$backup_receipt"; fi
  exit "$exit_code"
}
trap rollback ERR

echo "Ensuring PostgreSQL is healthy before backup"
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" up -d database

# Fail closed on a missing or failed database probe. A network or credential
# error must never be mistaken for an empty first-install database.
if ! has_schema="$(docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" exec -T database \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT to_regclass('public.users') IS NOT NULL;" 2>/dev/null)"; then
  schema_integrity_uncertain=1
  echo "Database schema probe failed; refusing deployment without a known backup state" >&2
  false
fi
case "$has_schema" in
  t)
    backup_receipt="$(mktemp "$STATE_DIR/backup-receipt.XXXXXXXX")"
    BACKUP_RECEIPT_FILE="$backup_receipt" bash ops/backup_postgres.sh "$CURRENT_ENV"
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
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" pull migrate seed backend worker frontend nginx caddy

echo "Applying migrations and starting release ${RELEASE_SHA}"
release_mutation_started=1
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
  exit 1
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
  --max-p95-ms "$MAX_P95_MS" \
  --max-error-rate "$MAX_ERROR_RATE"

trap - ERR
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
rm -f -- "$RECOVERY_REQUIRED"
echo "Deployment succeeded: ${RELEASE_SHA}"
