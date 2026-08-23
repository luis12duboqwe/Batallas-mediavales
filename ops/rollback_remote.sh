#!/usr/bin/env bash
set -euo pipefail

CURRENT_RELEASE="${1:-}"
CONFIRMATION="${2:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.deploy.yml}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

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
if [[ "$CONFIRMATION" != "ROLLBACK:${CURRENT_RELEASE}" ]]; then
  echo "Rollback refused. Re-run with confirmation: ROLLBACK:${CURRENT_RELEASE}" >&2
  exit 2
fi

STATE_DIR=".ops-state"
MANIFEST="$STATE_DIR/deployments/${CURRENT_RELEASE}.json"
if [[ ! -f "$MANIFEST" ]]; then
  echo "Rollback manifest not found: $MANIFEST" >&2
  exit 2
fi

eval "$(python3 - "$MANIFEST" <<'PY'
import json
import shlex
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
for key in ('previous_release_sha', 'rollback_backup'):
    value = payload.get(key) or ''
    print(f'{key.upper()}={shlex.quote(value)}')
PY
)"

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

cp "$PREVIOUS_ENV" .release.env
chmod 600 .release.env

if [[ -n "$ROLLBACK_BACKUP" ]]; then
  if [[ ! -f "$ROLLBACK_BACKUP" ]]; then
    echo "Rollback refused: database snapshot missing: $ROLLBACK_BACKUP" >&2
    exit 2
  fi
  bash ops/restore_postgres.sh .release.env "$ROLLBACK_BACKUP" "RESTORE:${POSTGRES_DB}"
else
  echo "No database snapshot was associated with this deployment; rolling back application images only"
  docker compose --env-file .release.env -f "$COMPOSE_FILE" pull backend worker frontend
  docker compose --env-file .release.env -f "$COMPOSE_FILE" up -d --remove-orphans backend worker frontend nginx caddy
fi

python3 ops/smoke_http.py --base-url "$PUBLIC_BASE_URL" --requests 20 --max-p95-ms 750
echo "$PREVIOUS_RELEASE_SHA" > .release-sha
chmod 600 .release-sha
echo "Rollback succeeded: ${CURRENT_RELEASE} -> ${PREVIOUS_RELEASE_SHA}"
