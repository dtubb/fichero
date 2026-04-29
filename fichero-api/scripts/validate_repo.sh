#!/bin/bash
set -u

# Run cross-repo validation checks from repo root.
# This script reports all results and exits non-zero if any check fails.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

API_ROOT="$ROOT_DIR/fichero-api"

if [ -n "${FICHERO_PYTHON_BIN:-}" ] && [ -x "${FICHERO_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FICHERO_PYTHON_BIN}"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [ -x "$API_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$API_ROOT/.venv/bin/python"
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

FAILURES=0

run_check() {
  local name="$1"
  shift
  echo
  echo "=== $name ==="
  if "$@"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    FAILURES=$((FAILURES + 1))
  fi
}

run_check "SwiftLint" swiftlint lint fichero-swiftui/fichero-swiftui/
run_check "Xcode build" xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero -configuration Debug build
run_check "Xcode tests" xcodebuild test -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero -destination "platform=macOS" -quiet
run_check "Pylint (errors only)" env PYTHONPATH=fichero-api/src "$PYTHON_BIN" -m pylint --rcfile=fichero-api/.pylintrc --errors-only fichero-api/src/fichero fichero-api/src/fichero_engine
run_check "Pytest unit" env PYTHONPATH=fichero-api/src "$PYTHON_BIN" -m pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived -q

run_check "OpenAPI sync script" ./fichero-api/scripts/sync_openapi_schema.sh
run_check "OpenAPI parity check" cmp -s \
  fichero-api/tests/contracts/openapi.json \
  fichero-swiftui/fichero-api-client/Sources/FicheroAPIClient/openapi.json

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "✅ All validation checks passed"
  exit 0
else
  echo "❌ Validation finished with $FAILURES failing check(s)"
  exit 1
fi
