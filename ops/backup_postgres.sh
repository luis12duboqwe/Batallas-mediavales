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

# Distinct invocations within the same second must never share a temporary or
# published filename. The staging directory stays private until verification.
umask 077
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage_dir="$(mktemp -d "$BACKUP_DIR/.${POSTGRES_DB}-${timestamp}.XXXXXXXX")"
nonce="${stage_dir##*.}"
backup="$BACKUP_DIR/${POSTGRES_DB}-${timestamp}-${nonce}.dump"
checksum="${backup}.sha256"
tmp="$stage_dir/archive.tmp"
checksum_tmp="$stage_dir/checksum.tmp"
backup_published=0
checksum_published=0
verified=0

cleanup() {
  if [[ "$verified" != 1 ]]; then
    if [[ "$checksum_published" == 1 ]]; then rm -f -- "$checksum"; fi
    if [[ "$backup_published" == 1 ]]; then rm -f -- "$backup"; fi
  fi
  rm -rf -- "$stage_dir"
}
trap cleanup EXIT

echo "Creating PostgreSQL backup: $backup"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$tmp"

test -s "$tmp"
hash="$(sha256sum "$tmp" | cut -d' ' -f1)"
printf '%s  %s\n' "$hash" "$backup" > "$checksum_tmp"
# Hard links atomically publish complete files and refuse existing names.
# Both links are on BACKUP_DIR's filesystem by construction.
ln -- "$tmp" "$backup"
backup_published=1
ln -- "$checksum_tmp" "$checksum"
checksum_published=1
sha256sum --check "$checksum"

find "$BACKUP_DIR" -type f \
  \( -name "${POSTGRES_DB}-*.dump" -o -name "${POSTGRES_DB}-*.dump.sha256" \) \
  -mtime "+$BACKUP_RETENTION_DAYS" -delete

# Deployment callers need the exact archive produced by THIS invocation.
# Never infer a rollback snapshot from the latest file in BACKUP_DIR:
# another backup run may finish concurrently.
if [[ -n "${BACKUP_RECEIPT_FILE:-}" ]]; then
  if [[ ! -f "$BACKUP_RECEIPT_FILE" || -L "$BACKUP_RECEIPT_FILE" ]]; then
    echo "Backup receipt must be an existing regular file" >&2
    exit 2
  fi
  printf '%s\n' "$backup" > "$BACKUP_RECEIPT_FILE"
  chmod 600 "$BACKUP_RECEIPT_FILE"
fi
verified=1
echo "Backup verified: $backup"
