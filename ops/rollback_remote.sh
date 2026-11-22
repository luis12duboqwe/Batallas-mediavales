#!/usr/bin/env bash
set -euo pipefail

CURRENT_RELEASE="${1:-}"
CONFIRMATION="${2:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# Manual rollback must be exclusive with a deployment or another rollback.
# Acquire the same lock before reading any active-release metadata.
STATE_DIR=".ops-state"
if [[ ! -d "$STATE_DIR" ]]; then
  echo "Rollback refused: deployment state directory missing" >&2
  exit 2
fi
umask 077
exec {DEPLOY_LOCK_FD}>> "$STATE_DIR/deploy.lock"
if ! flock -n "$DEPLOY_LOCK_FD"; then
  echo "Rollback refused: another deploy or rollback is already running" >&2
  exit 2
fi

if [[ -z "$CURRENT_RELEASE" ]]; then
  if [[ ! -f .release-sha ]]; then
    echo "Usage: $0 <current-release-sha> ROLLBACK:<current-release-sha>" >&2
    exit 2
  fi
  CURRENT_RELEASE="$(tr -d '[:space:]' < .release-sha)"
fi
if [[ ! "$CURRENT_RELEASE" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Current release must be a full 40-character git SHA" >&2
  exit 2
fi
if [[ ! -f .release-sha || ! -f .release.env ]]; then
  echo "Rollback refused: active release metadata is missing" >&2
  exit 2
fi
ACTIVE_RELEASE="$(tr -d '[:space:]' < .release-sha)"
if [[ "$ACTIVE_RELEASE" != "$CURRENT_RELEASE" ]]; then
  echo "Rollback refused: current release does not match active release" >&2
  exit 2
fi
if [[ "$CONFIRMATION" != "ROLLBACK:${CURRENT_RELEASE}" ]]; then
  echo "Rollback refused. Re-run with confirmation: ROLLBACK:${CURRENT_RELEASE}" >&2
  exit 2
fi

MANIFEST="$STATE_DIR/deployments/${CURRENT_RELEASE}.json"
if [[ ! -f "$MANIFEST" ]]; then
  echo "Rollback manifest not found: $MANIFEST" >&2
  exit 2
fi

MANIFEST_VALUES="$(python3 - "$MANIFEST" <<'PY'
import json
import shlex
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
for key in ('previous_release_sha', 'rollback_backup'):
    value = payload.get(key) or ''
    print(f'{key.upper()}={shlex.quote(value)}')
PY
)" || {
  echo "Rollback refused: manifest parse failed" >&2
  exit 2
}
unset PREVIOUS_RELEASE_SHA ROLLBACK_BACKUP
eval "$MANIFEST_VALUES"

if [[ ! "$PREVIOUS_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Rollback refused: deployment has no previous release" >&2
  exit 2
fi
PREVIOUS_ENV="$STATE_DIR/releases/${PREVIOUS_RELEASE_SHA}.env"
if [[ ! -f "$PREVIOUS_ENV" ]]; then
  echo "Rollback refused: previous release environment missing: $PREVIOUS_ENV" >&2
  exit 2
fi

python3 ops/preflight.py "$PREVIOUS_ENV"
eval "$(python3 - "$PREVIOUS_ENV" <<'PY'
import shlex
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env
values = read_env(Path(sys.argv[1]))
for key in ('POSTGRES_DB', 'PUBLIC_BASE_URL'):
    print(f'{key}={shlex.quote(values[key])}')
PY
)"

# Validate the snapshot before changing any active release pointer or service.
if [[ -n "$ROLLBACK_BACKUP" && ! -f "$ROLLBACK_BACKUP" ]]; then
  echo "Rollback refused: database snapshot missing: $ROLLBACK_BACKUP" >&2
  exit 2
fi

# Keep the active configuration and release pointer unchanged until the restore
# and smoke check have BOTH succeeded. The candidates live on the same filesystem
# as their destinations so each final rename is atomic.
STAGED_ENV="$(mktemp ./.release.env.rollback.XXXXXXXX)"
STAGED_SHA="$(mktemp ./.release-sha.rollback.XXXXXXXX)"
RECOVERY_REQUIRED="$STATE_DIR/recovery-required"
VALIDATED_BACKUP=""
RECOVERY_MARKER_PREEXISTED=0
if [[ -e "$RECOVERY_REQUIRED" || -L "$RECOVERY_REQUIRED" ]]; then
  RECOVERY_MARKER_PREEXISTED=1
fi
RECOVERY_MARKER_TMP=""
cleanup() {
  rm -f -- "$STAGED_ENV" "$STAGED_SHA" "$RECOVERY_MARKER_TMP"
  if [[ -n "$VALIDATED_BACKUP" ]]; then
    rm -rf -- "${VALIDATED_BACKUP%/*}"
  fi
}
trap cleanup EXIT
cp "$PREVIOUS_ENV" "$STAGED_ENV"
chmod 600 "$STAGED_ENV"
printf '%s\n' "$PREVIOUS_RELEASE_SHA" > "$STAGED_SHA"
chmod 600 "$STAGED_SHA"

# Validate and freeze the exact snapshot before publishing a recovery marker.
# A rejected checksum or archive identity must not create a false incident.
if [[ -n "$ROLLBACK_BACKUP" ]]; then
  VALIDATED_BACKUP="$(DEPLOY_LOCK_FD="$DEPLOY_LOCK_FD" RESTORE_PREPARE_ONLY=1 RESTORE_START_SERVICES=0 \
    bash ops/restore_postgres.sh "$STAGED_ENV" "$ROLLBACK_BACKUP" "RESTORE:${POSTGRES_DB}")"
  if [[ ! "$VALIDATED_BACKUP" =~ ^\.ops-state/restore\.[[:alnum:]]{8}/archive\.dump$ ||
        ! -s "$VALIDATED_BACKUP" || -L "$VALIDATED_BACKUP" ]]; then
    echo "Rollback refused: restore preflight did not return a private verified snapshot" >&2
    exit 2
  fi
fi

# A failed restore or smoke can leave the live database/services inconsistent
# with the active release pointers. Block future deploys before any mutation.
if [[ "$RECOVERY_MARKER_PREEXISTED" -eq 0 ]]; then
  RECOVERY_MARKER_TMP="$(mktemp "$STATE_DIR/recovery-required.XXXXXXXX")"
  printf 'reason=manual_rollback_in_progress\ncurrent_release=%s\nprevious_release=%s\n' \
    "$CURRENT_RELEASE" "$PREVIOUS_RELEASE_SHA" > "$RECOVERY_MARKER_TMP"
  chmod 600 "$RECOVERY_MARKER_TMP"
  mv -f -- "$RECOVERY_MARKER_TMP" "$RECOVERY_REQUIRED"
fi

if [[ -n "$ROLLBACK_BACKUP" ]]; then
  DEPLOY_LOCK_FD="$DEPLOY_LOCK_FD" RESTORE_PREPARE_ONLY=0 RESTORE_START_SERVICES=1 \
    bash ops/restore_postgres.sh "$STAGED_ENV" "$VALIDATED_BACKUP" "RESTORE:${POSTGRES_DB}"
else
  echo "No database snapshot was associated with this deployment; rolling back application images only"
  docker compose --env-file "$STAGED_ENV" -f "$COMPOSE_FILE" pull backend worker frontend
  docker compose --env-file "$STAGED_ENV" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx caddy
fi

python3 ops/smoke_http.py --base-url "$PUBLIC_BASE_URL" --requests 20 --max-p95-ms 750

# Commit metadata only after the candidate release has passed post-rollback smoke.
mv -f -- "$STAGED_ENV" .release.env
mv -f -- "$STAGED_SHA" .release-sha
if [[ "$RECOVERY_MARKER_PREEXISTED" -eq 0 ]]; then
  rm -f -- "$RECOVERY_REQUIRED"
fi
echo "Rollback succeeded: ${CURRENT_RELEASE} -> ${PREVIOUS_RELEASE_SHA}"
