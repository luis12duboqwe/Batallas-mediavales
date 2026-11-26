#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="/tmp/bm-g5-ci.env"
BAD_ENV_FILE="/tmp/bm-g5-ci-bad.env"
BAD_TLS_ENV_FILE="/tmp/bm-g5-ci-bad-tls.env"
BACKUP_DIR="/tmp/bm-g5-backups"
FAKE_DOCKER_DIR=""
FAKE_DATE_DIR=""
BACKUP_RECEIPT=""
COMPOSE_FILE="docker-compose.deploy.yml"
PROJECT_NAME="bm-g5-ci"
SMOKE_PID=""
ROLE_SPLIT_ENV=""

cleanup() {
  if [[ -n "$SMOKE_PID" ]]; then
    kill "$SMOKE_PID" 2>/dev/null || true
  fi
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BACKUP_DIR" "$ENV_FILE" "$BAD_ENV_FILE" "$BAD_TLS_ENV_FILE"
  if [[ -n "$ROLE_SPLIT_ENV" ]]; then rm -f -- "$ROLE_SPLIT_ENV"; fi
  if [[ -n "$FAKE_DOCKER_DIR" ]]; then rm -rf "$FAKE_DOCKER_DIR"; fi
  if [[ -n "$FAKE_DATE_DIR" ]]; then rm -rf "$FAKE_DATE_DIR"; fi
  if [[ -n "$BACKUP_RECEIPT" ]]; then rm -f -- "$BACKUP_RECEIPT"; fi
}
trap cleanup EXIT

rm -rf "$BACKUP_DIR"
cat > "$ENV_FILE" <<'EOF'
APP_ENV=staging
SECRET_KEY=ci-only-secret-key-that-is-long-enough-1234567890
PUBLIC_HOST=staging.example.invalid
FRONTEND_URL=https://staging.example.invalid
PUBLIC_BASE_URL=https://staging.example.invalid
CORS_ORIGINS=https://staging.example.invalid
TLS_EMAIL=ops@example.invalid
HTTP_PORT=18080
HTTPS_PORT=18443
POSTGRES_USER=batalla
POSTGRES_PASSWORD=ci-password
POSTGRES_DB=batalla_ci
DB_URL=postgresql+psycopg://batalla:ci-password@database:5432/batalla_ci
SMTP_HOST=smtp.example.invalid
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_STARTTLS=true
FROM_EMAIL=no-reply@example.invalid
SUPPORT_CONTACT=support@example.invalid
BACKEND_IMAGE=example.invalid/batalla-backend:0123456789abcdef0123456789abcdef01234567
FRONTEND_IMAGE=example.invalid/batalla-frontend:0123456789abcdef0123456789abcdef01234567
BACKUP_DIR=/tmp/bm-g5-backups
BACKUP_RETENTION_DAYS=7
LOAD_DURATION_SECONDS=2
LOAD_CONCURRENCY=4
MAX_P95_MS=750
MAX_ERROR_RATE=0
EOF

python3 ops/preflight.py "$ENV_FILE"

cp "$ENV_FILE" "$BAD_ENV_FILE"
sed -i 's#FRONTEND_IMAGE=.*#FRONTEND_IMAGE=example.invalid/batalla-frontend:latest#' "$BAD_ENV_FILE"
if python3 ops/preflight.py "$BAD_ENV_FILE"; then
  echo "Expected preflight to reject :latest image" >&2
  exit 1
fi

cp "$ENV_FILE" "$BAD_TLS_ENV_FILE"
sed -i 's#PUBLIC_HOST=.*#PUBLIC_HOST=other.example.invalid#' "$BAD_TLS_ENV_FILE"
if python3 ops/preflight.py "$BAD_TLS_ENV_FILE"; then
  echo "Expected preflight to reject a TLS hostname mismatch" >&2
  exit 1
fi

for script in ops/*.sh; do
  bash -n "$script"
done
python3 -m compileall -q ops

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q

# G5 role routing stays opt-in and MUST NEVER silently reuse DB_URL for
# migrate/seed. Verify actual Docker Compose interpolation, not source text.
ROLE_SPLIT_ENV="$(mktemp /tmp/bm-g5-role-split.XXXXXXXX)"
cp "$ENV_FILE" "$ROLE_SPLIT_ENV"
sed -i 's#^DB_URL=.*#DB_URL=postgresql+psycopg://game_app:synthetic-game-credential@database:5432/batalla_ci#' "$ROLE_SPLIT_ENV"
printf '%s\n' 'G5_MIGRATION_DB_URL=postgresql+psycopg://batalla:ci-password@database:5432/batalla_ci' >> "$ROLE_SPLIT_ENV"
python3 - "$ROLE_SPLIT_ENV" <<'PY'
import sys
from pathlib import Path
from ops.g5_migration_role_identity import validate_split
from ops.preflight import read_env
identity = validate_split(read_env(Path(sys.argv[1])))
if identity.application != "game_app" or identity.maintenance != "batalla":
    raise SystemExit("Isolated G5 role split preflight returned wrong identities")
PY
if docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" -f docker-compose.g5-migration.yml config -q >/dev/null 2>&1; then
  echo "Unsafe G5 overlay rendered without dedicated migration URL" >&2
  exit 1
fi
docker compose -p "$PROJECT_NAME" --env-file "$ROLE_SPLIT_ENV" \
  -f "$COMPOSE_FILE" -f docker-compose.g5-migration.yml config --format json |
python3 -c '
import json, sys
from urllib.parse import urlsplit
services=json.load(sys.stdin)["services"]
urls={name:services[name]["environment"]["DATABASE_URL"]
      for name in ("backend","worker","migrate","seed")}
if not (urls["backend"]==urls["worker"] and
        urls["migrate"]==urls["seed"] and
        urlsplit(urls["backend"]).username=="game_app" and
        urlsplit(urls["migrate"]).username=="batalla"):
    raise SystemExit("G5 composed services did not keep app/migration identities separate")
print("G5 opt-in migration role routing verified (no services started)")
'


docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d database
postgres_ready=0
for _ in $(seq 1 60); do
  if docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
    pg_isready -h 127.0.0.1 -U batalla -d batalla_ci >/dev/null 2>&1; then
    postgres_ready=1
    break
  fi
  sleep 1
done
if [[ "$postgres_ready" -ne 1 ]]; then
  echo "PostgreSQL did not become ready within the recovery gate window" >&2
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2 || true
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs database >&2 || true
  exit 1
fi

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE recovery_probe (id integer primary key, marker text not null); INSERT INTO recovery_probe VALUES (1, 'before-backup');"

BACKUP_RECEIPT="$(mktemp /tmp/bm-g5-backup-receipt.XXXXXXXX)"
COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" \
  BACKUP_RECEIPT_FILE="$BACKUP_RECEIPT" bash ops/backup_postgres.sh "$ENV_FILE"
test -s "$BACKUP_RECEIPT"
IFS= read -r BACKUP_FILE < "$BACKUP_RECEIPT"
test -s "$BACKUP_FILE"
sha256sum --check "${BACKUP_FILE}.sha256"
rm -f -- "$BACKUP_RECEIPT"
BACKUP_RECEIPT=""

# Force two backups to share the exact same second. Both must survive intact.
FAKE_DATE_DIR="$(mktemp -d /tmp/bm-g5-fixed-date.XXXXXXXX)"
REAL_DATE="$(command -v date)"
cat > "$FAKE_DATE_DIR/date" <<'SH'
#!/usr/bin/env bash
if [[ "$#" -eq 2 && "$1" == "-u" && "$2" == "+%Y%m%dT%H%M%SZ" ]]; then
  printf '20991231T235959Z\n'
else
  exec "$BM_REAL_DATE" "$@"
fi
SH
chmod 700 "$FAKE_DATE_DIR/date"
# Start both backups before waiting: this covers real overlap, not just
# sequential runs that happen to share a timestamp.
BACKUP_PIDS=()
for run in 1 2; do
  BM_REAL_DATE="$REAL_DATE" PATH="$FAKE_DATE_DIR:$PATH" \
    COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" \
    bash ops/backup_postgres.sh "$ENV_FILE" > "$BACKUP_DIR/concurrent-$run.log" 2>&1 &
  BACKUP_PIDS+=("$!")
done
backup_failed=0
for pid in "${BACKUP_PIDS[@]}"; do
  if ! wait "$pid"; then backup_failed=1; fi
done
if [[ "$backup_failed" != "0" ]]; then
  cat "$BACKUP_DIR"/concurrent-*.log >&2
  echo "Overlapping PostgreSQL backups failed" >&2
  exit 1
fi
mapfile -t SAME_SECOND_BACKUPS < <(find "$BACKUP_DIR" -maxdepth 1 -type f \
  -name 'batalla_ci-20991231T235959Z-*.dump' | sort)
if [[ "${#SAME_SECOND_BACKUPS[@]}" -ne 2 ]]; then
  echo "Concurrent-second backups collided or disappeared" >&2
  exit 1
fi
for archive in "${SAME_SECOND_BACKUPS[@]}"; do
  test -s "$archive"
  sha256sum --check "${archive}.sha256"
done

# Retention is scoped to published files in the backup root. A stale-looking
# nested archive may belong to a separate operation and must not be touched.
mkdir -p "$BACKUP_DIR/.retention-scope-probe"
NESTED_ARCHIVE="$BACKUP_DIR/.retention-scope-probe/batalla_ci-old.dump"
OLD_ARCHIVE="$BACKUP_DIR/batalla_ci-retention-probe.dump"
printf 'nested archive\n' > "$NESTED_ARCHIVE"
printf 'expired archive\n' > "$OLD_ARCHIVE"
sha256sum "$NESTED_ARCHIVE" > "${NESTED_ARCHIVE}.sha256"
sha256sum "$OLD_ARCHIVE" > "${OLD_ARCHIVE}.sha256"
touch -d '30 days ago' "$NESTED_ARCHIVE" "${NESTED_ARCHIVE}.sha256" "$OLD_ARCHIVE" "${OLD_ARCHIVE}.sha256"
COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" \
  bash ops/backup_postgres.sh "$ENV_FILE"
test ! -e "$OLD_ARCHIVE"
test ! -e "${OLD_ARCHIVE}.sha256"
sha256sum --check "${NESTED_ARCHIVE}.sha256"
for archive in "${SAME_SECOND_BACKUPS[@]}"; do
  sha256sum --check "${archive}.sha256"
done
rm -r -- "$BACKUP_DIR/.retention-scope-probe"

# A failed pg_dump must leave no half-written backup, no orphan checksum,
# and no leaked staging directory; the successful backups must remain usable.
DUMP_COUNT_BEFORE="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'batalla_ci-*.dump' | wc -l)"
FAKE_DOCKER_DIR="$(mktemp -d /tmp/bm-g5-fail-dump.XXXXXX)"
REAL_DOCKER="$(command -v docker)"
cat > "$FAKE_DOCKER_DIR/docker" <<'SH'
#!/usr/bin/env bash
if [[ " $* " == *" pg_dump "* ]]; then
  printf 'partial PostgreSQL dump'
  exit 73
fi
exec "$BM_REAL_DOCKER" "$@"
SH
chmod 700 "$FAKE_DOCKER_DIR/docker"
if BM_REAL_DOCKER="$REAL_DOCKER" PATH="$FAKE_DOCKER_DIR:$PATH" \
  COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" \
  bash ops/backup_postgres.sh "$ENV_FILE"; then
  echo "Backup unexpectedly succeeded after an injected pg_dump failure" >&2
  exit 1
fi
DUMP_COUNT_AFTER="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'batalla_ci-*.dump' | wc -l)"
if [[ "$DUMP_COUNT_AFTER" != "$DUMP_COUNT_BEFORE" ]]; then
  echo "Failed pg_dump left a published archive or deleted a valid one" >&2
  exit 1
fi
if find "$BACKUP_DIR" -maxdepth 1 -type d -name '.batalla_ci-*' | grep -q .; then
  echo "Failed pg_dump leaked a staging directory" >&2
  exit 1
fi
for archive in "${SAME_SECOND_BACKUPS[@]}"; do
  sha256sum --check "${archive}.sha256"
done
rm -rf "$FAKE_DOCKER_DIR"
FAKE_DOCKER_DIR=""

# Retain the exact backup returned by the first pg_dump invocation even
# after other later/concurrent backups have populated BACKUP_DIR.
test -n "$BACKUP_FILE"
test -s "$BACKUP_FILE"
test -s "${BACKUP_FILE}.sha256"

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci -v ON_ERROR_STOP=1 -c \
  "UPDATE recovery_probe SET marker='after-backup' WHERE id=1;"

# A valid, checksummed dump from a different database must be refused
# without stopping services or altering the current database.
FOREIGN_BACKUP="$BACKUP_DIR/foreign-ci.dump"
docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  createdb -U batalla foreign_ci
docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_dump --format=custom --no-owner --no-privileges -U batalla -d foreign_ci > "$FOREIGN_BACKUP"
sha256sum "$FOREIGN_BACKUP" > "${FOREIGN_BACKUP}.sha256"
if COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" RESTORE_START_SERVICES=0 \
  bash ops/restore_postgres.sh "$ENV_FILE" "$FOREIGN_BACKUP" "RESTORE:batalla_ci"; then
  echo "Wrong-database archive was accepted by restore_postgres.sh" >&2
  exit 1
fi
CURRENT_MARKER="$(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci -Atqc "SELECT marker FROM recovery_probe WHERE id=1;")"
if [[ "$CURRENT_MARKER" != "after-backup" ]]; then
  echo "Refused restore unexpectedly changed the database: '$CURRENT_MARKER'" >&2
  exit 1
fi

# Corrupt a copied archive but keep a checksum pointing at the healthy source.
TAMPERED_BACKUP="$BACKUP_DIR/tampered-ci.dump"
cp "$BACKUP_FILE" "$TAMPERED_BACKUP"
cp "${BACKUP_FILE}.sha256" "${TAMPERED_BACKUP}.sha256"
printf 'intentional-corruption' >> "$TAMPERED_BACKUP"
if COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" RESTORE_START_SERVICES=0 \
  bash ops/restore_postgres.sh "$ENV_FILE" "$TAMPERED_BACKUP" "RESTORE:batalla_ci"; then
  echo "Checksum for a different file wrongly accepted a tampered archive" >&2
  exit 1
fi

# Inject a Docker stop failure; restore must refuse before touching the DB.
FAKE_DOCKER_DIR="$(mktemp -d /tmp/bm-g5-fail-stop.XXXXXX)"
REAL_DOCKER="$(command -v docker)"
cat > "$FAKE_DOCKER_DIR/docker" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"stop backend worker"* ]]; then
  echo "Injected refusal to stop application writers" >&2
  exit 73
fi
exec "$BM_REAL_DOCKER" "$@"
SH
chmod 700 "$FAKE_DOCKER_DIR/docker"
if BM_REAL_DOCKER="$REAL_DOCKER" PATH="$FAKE_DOCKER_DIR:$PATH" \
  COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" RESTORE_START_SERVICES=0 \
  bash ops/restore_postgres.sh "$ENV_FILE" "$BACKUP_FILE" "RESTORE:batalla_ci"; then
  echo "Restore continued despite failure to stop writers" >&2
  exit 1
fi

CURRENT_MARKER="$(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci -Atqc "SELECT marker FROM recovery_probe WHERE id=1;")"
if [[ "$CURRENT_MARKER" != "after-backup" ]]; then
  echo "Refused fail-closed restore unexpectedly changed the database: '$CURRENT_MARKER'" >&2
  exit 1
fi

# The injected stop failure published a durable recovery incident. Do not
# bypass or clear that marker to restore an older archive into the live DB.
# Validate the snapshot instead in a separate disposable destination database.
if [[ ! -s .ops-state/recovery-required ]]; then
  echo "Refused restore did not preserve its recovery incident" >&2
  exit 1
fi
docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  createdb -U batalla batalla_ci_restore_probe
docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_restore --no-owner --no-privileges --exit-on-error -U batalla -d batalla_ci_restore_probe < "$BACKUP_FILE"
RESTORED_MARKER="$(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci_restore_probe -Atqc "SELECT marker FROM recovery_probe WHERE id=1;")"
if [[ "$RESTORED_MARKER" != "before-backup" ]]; then
  echo "Isolated backup/restore drill failed: got marker '$RESTORED_MARKER'" >&2
  exit 1
fi
CURRENT_MARKER="$(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -h 127.0.0.1 -U batalla -d batalla_ci -Atqc "SELECT marker FROM recovery_probe WHERE id=1;")"
if [[ "$CURRENT_MARKER" != "after-backup" ]]; then
  echo "Isolation failure: restore drill modified source database" >&2
  exit 1
fi

python3 - <<'PY' >/tmp/bm-g5-smoke-server.log 2>&1 &
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/health", "/api/health"}:
            body = b"ok\n"
            content_type = "text/plain"
        elif self.path == "/api/economy/balance_preview":
            body = json.dumps({"version": "ci-g5"}).encode()
            content_type = "application/json"
        elif self.path == "/":
            body = b"<!doctype html><title>Batalla Medieval CI</title>"
            content_type = "text/html"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

ThreadingHTTPServer(("127.0.0.1", 18765), Handler).serve_forever()
PY
SMOKE_PID=$!

smoke_ready=0
for _ in $(seq 1 20); do
  if python3 - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:18765/health', timeout=1).read()
PY
  then
    smoke_ready=1
    break
  fi
  sleep 0.25
done
if [[ "$smoke_ready" -ne 1 ]]; then
  echo "Local smoke fixture did not become ready" >&2
  cat /tmp/bm-g5-smoke-server.log >&2 || true
  exit 1
fi

python3 ops/smoke_http.py --base-url http://127.0.0.1:18765 --allow-http --requests 10 --max-p95-ms 750
python3 ops/load_smoke.py --base-url http://127.0.0.1:18765 --allow-http --duration-seconds 2 --concurrency 4 --max-p95-ms 750 --max-error-rate 0

# The isolated writer shutdown fixture is mandatory in GitHub CI, where
# it uses only disposable containers in a random synthetic project.
if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
  CI=true python3 -m ops.ci_g5_docker_writer_fence
fi

echo "G5 operations verification passed"
