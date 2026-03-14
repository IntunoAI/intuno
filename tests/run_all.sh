#!/usr/bin/env bash
# Run all workflow tests against a live backend.
#
# Prerequisites:
#   1. Backend:  cd wisdom && uvicorn src.main:app --reload
#   2. Demo agent: cd wisdom/demo && python -m uvicorn agents.calculator_agent:app --port 8001
#
# Usage:
#   bash tests/run_all.sh                           # defaults to localhost:8000
#   bash tests/run_all.sh http://my-server:8000     # custom URL

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "============================================"
echo "  Running Wisdom test suite"
echo "  Backend: $BASE_URL"
echo "============================================"
echo ""

# Inject agent credentials so broker→agent calls succeed (wisdom-agents requires X-API-Key)
AGENTS_ENV="$ROOT_DIR/../wisdom-agents/.env"
if [ -f "$AGENTS_ENV" ] && grep -q '^AGENTS_API_KEY=' "$AGENTS_ENV" 2>/dev/null; then
  AGENTS_API_KEY=$(grep '^AGENTS_API_KEY=' "$AGENTS_ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
  if [ -n "$AGENTS_API_KEY" ]; then
    echo ">> Injecting agent credentials (from wisdom-agents .env)"
    python scripts/inject_agent_credentials.py --api-key "$AGENTS_API_KEY" || true
  fi
fi

echo ""
echo ">> Backend workflow tests"
python -m tests.test_workflow --base-url "$BASE_URL"

echo ""
echo ">> SDK integration tests"
PYTHONPATH="$ROOT_DIR:$ROOT_DIR/../intuno_sdk" python -m tests.test_sdk_integration --base-url "$BASE_URL"

echo ""
echo ">> User session E2E tests"
python -m tests.test_user_session --base-url "$BASE_URL"

echo ""
echo "All test suites completed."
