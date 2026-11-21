#!/usr/bin/env bash
# Full isolated E2E on three disposable SQLite databases and loopback services.
# No production URLs, credentials, SMTP, or external actions.
set -euo pipefail

export APP_ENV=test
export PARALLEL_JOURNEY_ALLOW_MUTATIONS=isolated
export PYTHONPATH=batalla_medieval_backend
export VITE_API_URL=http://127.0.0.1:8188
export VITE_SOCKET_URL=http://127.0.0.1:8188
export E2E_BASE_URL=http://127.0.0.1:4288
export CORS_ORIGINS=http://127.0.0.1:4288
export FRONTEND_URL=http://127.0.0.1:4288
export PARALLEL_JOURNEY_PYTHON=python
export SECRET_KEY=ci-test-only-medievol-parallel-journey-key-do-not-use-in-production

: "$GITHUB_RUN_ID"
API_PID=0
UI_PID=0
LOG_DIR="/tmp/medievol-journey-ci-logs-$GITHUB_RUN_ID"
mkdir -p "$LOG_DIR"
cleanup() {
  status=$?
  trap - EXIT
  if (( API_PID > 0 )); then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi
  if (( UI_PID > 0 )); then kill "$UI_PID" 2>/dev/null || true; wait "$UI_PID" 2>/dev/null || true; fi
  if (( status != 0 )); then
    echo "Isolated E2E failed (exit=$status); last backend/frontend lines:"
    tail -70 "$LOG_DIR/backend.log" 2>/dev/null || true
    tail -40 "$LOG_DIR/frontend.log" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

create_db() {
  suite="$1"
  export PARALLEL_JOURNEY_DB="/tmp/medievol-journey-ci-$suite-$GITHUB_RUN_ID.db"
  export DATABASE_URL="sqlite:///$PARALLEL_JOURNEY_DB"
  if [[ -e "$PARALLEL_JOURNEY_DB" ]]; then echo "Refusing to reuse test database"; exit 2; fi
  echo "Preparing isolated $suite fixture"
  alembic -c batalla_medieval_backend/alembic.ini upgrade head
  python -m app.seed
}

stop_api() {
  if (( API_PID > 0 )); then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
    API_PID=0
  fi
}

start_api() {
  # Old services can be healthy but attached to another disposable database.
  # Do not mistake their HTTP 200 for this run's newly spawned backend.
  if curl --fail --silent --max-time 2 http://127.0.0.1:8188/health >/dev/null; then
    echo "Refusing to reuse a backend still listening on test port 8188" >&2
    return 1
  fi
  python -m uvicorn app.main:socket_app --app-dir batalla_medieval_backend \
    --host 127.0.0.1 --port 8188 >"$LOG_DIR/backend.log" 2>&1 &
  API_PID=$!
  for i in $(seq 1 60); do
    if curl --fail --silent http://127.0.0.1:8188/health >/dev/null; then return 0; fi
    if ! kill -0 "$API_PID" 2>/dev/null; then echo "Backend stopped"; return 1; fi
    sleep 1
  done
  echo "Backend did not become ready"; return 1
}

run_suite() {
  name="$1"
  shift
  echo "START isolated $name: $*"
  for test in "$@"; do
    echo "TEST $test"
    (cd batalla_medieval_frontend && node "e2e/parallel-journey-$test.mjs")
  done
  echo "PASS isolated $name"
}

# Frontend is built once; its API endpoint remains the same through DB rotation.
(cd batalla_medieval_frontend && npm run build)
(
  cd batalla_medieval_frontend
  exec ./node_modules/.bin/vite preview --host 127.0.0.1 --port 4288 --strictPort
) >"$LOG_DIR/frontend.log" 2>&1 &
UI_PID=$!
for i in $(seq 1 40); do
  if curl --fail --silent http://127.0.0.1:4288/login >/dev/null; then break; fi
  if ! kill -0 "$UI_PID" 2>/dev/null; then echo "Frontend stopped"; exit 1; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:4288/login >/dev/null

create_db core
python scripts/prepare_g2_e2e.py
python scripts/prepare_g7_research_e2e.py
python scripts/prepare_g8_unit_upkeep_e2e.py
python scripts/prepare_g9_combat_e2e.py
python scripts/prepare_g10_espionage_e2e.py
(cd batalla_medieval_frontend && node e2e/parallel-journey-fixtures.mjs)
start_api
# Focused state and browser regressions must run on a clean G2 login fixture,
# before the core journey mutates player sessions and world memberships.
(cd batalla_medieval_frontend && node --test e2e/parallel-adventures-state.mjs)
(cd batalla_medieval_frontend && node e2e/parallel-adventures-flow.mjs)
run_suite core onboarding progression queue-completion movement-target security crossworld map-actions
# Map accessibility, navigation and contextual actions are separate from
# the broad player-journey suites and must remain mandatory gates.
(cd batalla_medieval_frontend && node e2e/parallel-map-navigation.mjs)
(cd batalla_medieval_frontend && node e2e/parallel-map-actions-integration.mjs)
stop_api

create_db live
python scripts/prepare_g9_combat_e2e.py
python scripts/prepare_g10_espionage_e2e.py
start_api
run_suite live live-missions
stop_api

create_db singleplayer
start_api
run_suite singleplayer single-player
stop_api
# One more independent disposable database exercises the actual funded UI,
# rather than relying on HTTP-only unit tests or mocks.
create_db wonder
python scripts/prepare_g2_e2e.py
python scripts/prepare_g9_combat_e2e.py
python scripts/prepare_wonder_funding_e2e.py
start_api
run_suite wonder wonder-funding
stop_api
echo "PARALLEL_JOURNEY_ALL_10_SUITES_PASS"
