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
