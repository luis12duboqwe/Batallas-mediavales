#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"
BACKUP_FILE="${2:-}"
CONFIRMATION="${3:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <env-file> <backup.dump> RESTORE:<database>" >&2
  exit 2
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
sha256sum --check "$CHECKSUM_FILE"

echo "Stopping application writers before restore"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop backend worker || true

echo "Terminating remaining database client sessions"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();"

echo "Restoring $BACKUP_FILE into $POSTGRES_DB"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_restore --clean --if-exists --create --no-owner --no-privileges --exit-on-error \
  -U "$POSTGRES_USER" -d postgres < "$BACKUP_FILE"

echo "Starting services and applying the selected release migration"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx

echo "Restore completed. Run ops/smoke_http.py against PUBLIC_BASE_URL before ending maintenance."
