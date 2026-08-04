#!/usr/bin/env bash
#
# Same pipeline as docker-compose.test.yml, but running the service from the
# local conda env instead of a container.
#
# The containerised runner (./scripts/run_test_pipeline.sh) is the primary path.
# This local variant avoids a rebuild when iterating on a test, and works even
# without Docker running.
#
#   ./scripts/run_test_pipeline_local.sh
#
# Exit codes match the containerised runner: 0 pass, 1 failures, 2 nothing tested.

set -uo pipefail

cd "$(dirname "$0")/.."

CONDA_ENV="${CONDA_ENV:-/opt/homebrew/anaconda3/envs/vital-agent-resource-rest}"
PYTHON="${CONDA_ENV}/bin/python"
PORT="${TEST_PORT:-8018}"

if [ ! -x "${PYTHON}" ]; then
  echo "error: python not found at ${PYTHON}; set CONDA_ENV" >&2
  exit 2
fi

if [ ! -f .env ]; then
  echo "error: .env not found" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

# Self-contained: no Keycloak, matching the compose stack.
export DEV__JWT__ENABLED=false

if [ -z "${DEV__TOOL__GITHUB__PAT:-}" ] || [ -z "${GITHUB_TEST_OWNER:-}" ]; then
  echo "error: .env is missing DEV__TOOL__GITHUB__PAT or GITHUB_TEST_OWNER" >&2
  exit 2
fi

LOG=$(mktemp -t varr-test-service)
echo "--- starting service on :${PORT} (log: ${LOG}) ---"

PYTHONPATH=. "${PYTHON}" -m uvicorn vital_agent_resource_app.app:app \
  --host 127.0.0.1 --port "${PORT}" > "${LOG}" 2>&1 &
SERVICE_PID=$!

cleanup() {
  echo ""
  echo "--- stopping service (pid ${SERVICE_PID}) ---"
  kill "${SERVICE_PID}" 2>/dev/null
  wait "${SERVICE_PID}" 2>/dev/null
}
trap cleanup EXIT

# The test waits for /health itself, but bail out early with the server log if
# the process died on startup -- otherwise the failure looks like a timeout.
sleep 3
if ! kill -0 "${SERVICE_PID}" 2>/dev/null; then
  echo "error: service exited during startup" >&2
  tail -20 "${LOG}" >&2
  exit 2
fi

# Offline pagination suite first -- fast, and catches regressions the live
# sandbox cannot produce.
"${PYTHON}" tests/github_pagination_test.py
status=$?

if [ ${status} -eq 0 ]; then
  TOOL_SERVICE_URL="http://localhost:${PORT}" \
    "${PYTHON}" tests/github_tools_pipeline_test.py
  status=$?
fi

echo ""
if [ ${status} -eq 0 ]; then
  echo "PIPELINE PASSED"
else
  echo "PIPELINE FAILED (exit ${status})"
  echo "service log tail:"
  tail -20 "${LOG}"
fi

exit ${status}
