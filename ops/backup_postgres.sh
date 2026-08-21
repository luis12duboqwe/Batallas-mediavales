#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

python3 ops/preflight.py "$ENV_FILE"

eval "$(python3 - "$ENV_FILE" <<'PY'
import shlex
import sys
from pathlib import Path
sys.path.insert(0, 'ops')
from preflight import read_env
values = read_env(Path(sys.argv[1]))
for key in ('POSTGRES_USER', 'POSTGRES_DB', 'BACKUP_DIR', 'BACKUP_RETENTION_DAYS'):
    print(f'{key}={shlex.quote(values[key])}')
PY
)"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_DIR/${POSTGRES_DB}-${timestamp}.dump"
tmp="${backup}.tmp"
checksum="${backup}.sha256"

cleanup() {
  rm -f "$tmp"
}
trap cleanup EXIT

echo "Creating PostgreSQL backup: $backup"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$tmp"

test -s "$tmp"
mv "$tmp" "$backup"
chmod 600 "$backup"
sha256sum "$backup" > "$checksum"
chmod 600 "$checksum"
sha256sum --check "$checksum"

find "$BACKUP_DIR" -type f \
  \( -name "${POSTGRES_DB}-*.dump" -o -name "${POSTGRES_DB}-*.dump.sha256" \) \
  -mtime "+$BACKUP_RETENTION_DAYS" -delete

echo "Backup verified: $backup"
