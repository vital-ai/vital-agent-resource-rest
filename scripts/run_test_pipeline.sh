#!/usr/bin/env bash
#
# Run the ephemeral test stack end to end and exit with the suite's status.
#
#   ./scripts/run_test_pipeline.sh            # build, test, tear down
#   ./scripts/run_test_pipeline.sh --keep     # leave the stack running on :8018
#
# Exit codes come from the tests container: 0 pass, 1 failures, 2 nothing tested.

set -uo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE=docker-compose.test.yml
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

if [ ! -f .env ]; then
  echo "error: .env not found; the stack reads credentials from it" >&2
  exit 2
fi

# Fail early with a clear message rather than watching the suite report
# "nothing to test" from inside a container.
missing=""
for var in DEV__TOOL__GITHUB__PAT DEV__TOOL__GITHUB__ALLOWED_REPOS GITHUB_TEST_OWNER GITHUB_TEST_REPO; do
  grep -q "^${var}=" .env || missing="${missing} ${var}"
done
if [ -n "${missing}" ]; then
  echo "error: .env is missing:${missing}" >&2
  exit 2
fi

cleanup() {
  if [ "${KEEP}" -eq 0 ]; then
    echo ""
    echo "--- tearing down ---"
    docker compose -f "${COMPOSE_FILE}" down --remove-orphans >/dev/null 2>&1
  else
    echo ""
    echo "--- stack left running: http://localhost:8018 ---"
    echo "    docker compose -f ${COMPOSE_FILE} down"
  fi
}
trap cleanup EXIT

echo "--- building and running test pipeline ---"
docker compose -f "${COMPOSE_FILE}" up --build \
  --abort-on-container-exit --exit-code-from tests
status=$?

echo ""
if [ ${status} -eq 0 ]; then
  echo "PIPELINE PASSED"
else
  echo "PIPELINE FAILED (exit ${status})"
fi

exit ${status}
