#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-}"
HOUR_UTC="${BACKUP_HOUR_UTC:-3}"
MINUTE_UTC="${BACKUP_MINUTE_UTC:-17}"
MARKER_BEGIN="# BEGIN BATALLA_MEDIEVAL_BACKUP"
MARKER_END="# END BATALLA_MEDIEVAL_BACKUP"

if [[ -z "$APP_DIR" || "$APP_DIR" != /* ]]; then
  echo "Usage: $0 <absolute-app-directory>" >&2
  exit 2
fi
if [[ "$APP_DIR" == *$'\n'* || "$APP_DIR" == *$'\r'* ]]; then
  echo "Application directory contains invalid newline characters" >&2
  exit 2
fi
if ! [[ "$HOUR_UTC" =~ ^([0-9]|1[0-9]|2[0-3])$ ]]; then
  echo "BACKUP_HOUR_UTC must be an integer from 0 to 23" >&2
  exit 2
fi
if ! [[ "$MINUTE_UTC" =~ ^([0-9]|[1-5][0-9])$ ]]; then
  echo "BACKUP_MINUTE_UTC must be an integer from 0 to 59" >&2
  exit 2
fi
if [[ ! -f "$APP_DIR/docker-compose.deploy.yml" || ! -f "$APP_DIR/ops/backup_postgres.sh" ]]; then
  echo "Deployment bundle is incomplete in $APP_DIR" >&2
  exit 2
fi

mkdir -p "$APP_DIR/.ops-state"
chmod 700 "$APP_DIR/.ops-state"
LOG_FILE="$APP_DIR/.ops-state/backup-cron.log"
CURRENT="$(mktemp)"
FILTERED="$(mktemp)"
trap 'rm -f "$CURRENT" "$FILTERED"' EXIT

crontab -l > "$CURRENT" 2>/dev/null || true
awk -v begin="$MARKER_BEGIN" -v end="$MARKER_END" '
  $0 == begin {skip=1; next}
  $0 == end {skip=0; next}
  !skip {print}
' "$CURRENT" > "$FILTERED"

{
  cat "$FILTERED"
  echo "$MARKER_BEGIN"
  printf '%s %s * * * cd %q && COMPOSE_FILE=docker-compose.deploy.yml bash ops/backup_postgres.sh .release.env >> %q 2>&1\n' \
    "$MINUTE_UTC" "$HOUR_UTC" "$APP_DIR" "$LOG_FILE"
  echo "$MARKER_END"
} | crontab -

echo "Daily backup schedule installed for ${HOUR_UTC}:$(printf '%02d' "$MINUTE_UTC") UTC"
