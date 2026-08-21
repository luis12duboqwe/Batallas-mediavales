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
for key in ('POSTGRES_USER', 'POSTGRES_DB', 'BACKUP_DIR', 'PUBLIC_BASE_URL'):
    print(f'{key}={shlex.quote(values[key])}')
PY
)"

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
mv "$NEXT_ENV" "$CURRENT_ENV"

rollback_backup=""
rollback() {
  local exit_code=$?
  trap - ERR
  echo "Deployment failed; attempting controlled rollback" >&2
  if [[ "$had_previous" -eq 1 ]]; then
    cp "$PREVIOUS_ENV" "$CURRENT_ENV"
    chmod 600 "$CURRENT_ENV"
    if [[ -n "$rollback_backup" && -f "$rollback_backup" ]]; then
      echo "Restoring pre-deploy database snapshot and previous application release" >&2
      ops/restore_postgres.sh "$CURRENT_ENV" "$rollback_backup" "RESTORE:${POSTGRES_DB}" || true
    else
      echo "No database snapshot was created; restoring previous application images only" >&2
      docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" pull backend worker frontend || true
      docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx || true
    fi
    if [[ "$previous_release_sha" =~ ^[0-9a-f]{40}$ ]]; then
      echo "$previous_release_sha" > .release-sha
      chmod 600 .release-sha
    fi
  else
    echo "No previous release exists; leaving services for diagnosis" >&2
  fi
  exit "$exit_code"
}
trap rollback ERR

echo "Ensuring PostgreSQL is healthy before backup"
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" up -d database

has_schema="$(docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" exec -T database \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT to_regclass('public.users') IS NOT NULL;" 2>/dev/null || true)"
if [[ "$has_schema" == "t" ]]; then
  ops/backup_postgres.sh "$CURRENT_ENV"
  rollback_backup="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${POSTGRES_DB}-*.dump" -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
  if [[ -z "$rollback_backup" ]]; then
    echo "Backup completed but rollback snapshot could not be located" >&2
    exit 1
  fi
else
  echo "No existing application schema; treating this as first deployment"
fi

echo "Pulling immutable release images"
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" pull migrate seed backend worker frontend nginx

echo "Applying migrations and starting release ${RELEASE_SHA}"
docker compose --env-file "$CURRENT_ENV" -f "$COMPOSE_FILE" up -d --remove-orphans

echo "Running post-deploy smoke against ${PUBLIC_BASE_URL}"
python3 ops/smoke_http.py --base-url "$PUBLIC_BASE_URL" --requests 20 --max-p95-ms 750

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
echo "Deployment succeeded: ${RELEASE_SHA}"
