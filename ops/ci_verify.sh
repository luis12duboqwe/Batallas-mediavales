#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="/tmp/bm-g5-ci.env"
BAD_ENV_FILE="/tmp/bm-g5-ci-bad.env"
BACKUP_DIR="/tmp/bm-g5-backups"
COMPOSE_FILE="docker-compose.deploy.yml"
PROJECT_NAME="bm-g5-ci"
SMOKE_PID=""

cleanup() {
  if [[ -n "$SMOKE_PID" ]]; then
    kill "$SMOKE_PID" 2>/dev/null || true
  fi
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BACKUP_DIR" "$ENV_FILE" "$BAD_ENV_FILE"
}
trap cleanup EXIT

rm -rf "$BACKUP_DIR"
cat > "$ENV_FILE" <<'EOF'
APP_ENV=staging
SECRET_KEY=ci-only-secret-key-that-is-long-enough-1234567890
FRONTEND_URL=https://staging.example.invalid
PUBLIC_BASE_URL=https://staging.example.invalid
CORS_ORIGINS=https://staging.example.invalid
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
BACKEND_IMAGE=example.invalid/batalla-backend:0123456789abcdef0123456789abcdef01234567
FRONTEND_IMAGE=example.invalid/batalla-frontend:0123456789abcdef0123456789abcdef01234567
BACKUP_DIR=/tmp/bm-g5-backups
BACKUP_RETENTION_DAYS=7
HTTP_PORT=18080
EOF

python3 ops/preflight.py "$ENV_FILE"
cp "$ENV_FILE" "$BAD_ENV_FILE"
sed -i 's#FRONTEND_IMAGE=.*#FRONTEND_IMAGE=example.invalid/batalla-frontend:latest#' "$BAD_ENV_FILE"
if python3 ops/preflight.py "$BAD_ENV_FILE"; then
  echo "Expected preflight to reject :latest image" >&2
  exit 1
fi

for script in ops/*.sh; do
  bash -n "$script"
done
python3 -m compileall -q ops

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d database
for _ in $(seq 1 30); do
  if docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
    pg_isready -U batalla -d batalla_ci >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  pg_isready -U batalla -d batalla_ci

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -U batalla -d batalla_ci -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE recovery_probe (id integer primary key, marker text not null); INSERT INTO recovery_probe VALUES (1, 'before-backup');"

COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" bash ops/backup_postgres.sh "$ENV_FILE"
BACKUP_FILE="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'batalla_ci-*.dump' | sort | tail -n1)"
test -n "$BACKUP_FILE"
test -s "$BACKUP_FILE"
test -s "${BACKUP_FILE}.sha256"

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -U batalla -d batalla_ci -v ON_ERROR_STOP=1 -c \
  "UPDATE recovery_probe SET marker='after-backup' WHERE id=1;"

COMPOSE_FILE="$COMPOSE_FILE" COMPOSE_PROJECT_NAME="$PROJECT_NAME" RESTORE_START_SERVICES=0 \
  bash ops/restore_postgres.sh "$ENV_FILE" "$BACKUP_FILE" "RESTORE:batalla_ci"
RESTORED_MARKER="$(docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T database \
  psql -U batalla -d batalla_ci -Atqc "SELECT marker FROM recovery_probe WHERE id=1;")"
if [[ "$RESTORED_MARKER" != "before-backup" ]]; then
  echo "Backup/restore round trip failed: got marker '$RESTORED_MARKER'" >&2
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

for _ in $(seq 1 20); do
  if python3 - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:18765/health', timeout=1).read()
PY
  then
    break
  fi
  sleep 0.25
done

python3 ops/smoke_http.py --base-url http://127.0.0.1:18765 --allow-http --requests 10 --max-p95-ms 750
python3 ops/load_smoke.py --base-url http://127.0.0.1:18765 --allow-http --duration-seconds 2 --concurrency 4 --max-p95-ms 750 --max-error-rate 0

echo "G5 operations verification passed"
