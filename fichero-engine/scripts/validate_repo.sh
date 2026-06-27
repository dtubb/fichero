#!/bin/bash
set -u

# Run cross-repo validation checks from repo root.
# This script reports all results and exits non-zero if any check fails.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

API_ROOT="$ROOT_DIR/fichero-engine"

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

run_check "SwiftLint" swiftlint lint fichero/fichero/
run_check "Xcode build" xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -configuration Debug build
run_check "Xcode tests" xcodebuild test -project fichero/fichero.xcodeproj -scheme Fichero -destination "platform=macOS" -quiet
run_check "Pylint (errors only)" env PYTHONPATH=fichero-engine/src "$PYTHON_BIN" -m pylint --rcfile=fichero-engine/.pylintrc --errors-only fichero-engine/src/fichero fichero-engine/src/engine
run_check "Pytest unit" env PYTHONPATH=fichero-engine/src "$PYTHON_BIN" -m pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q

echo
echo "=== Architecture and tooling guardrails ==="
for GUARDRAIL in scripts/check_*.py; do
  GUARDRAIL_NAME="$(basename "$GUARDRAIL")"
  if [ "$GUARDRAIL_NAME" = "check_unmerged_work.py" ] || [ "$GUARDRAIL_NAME" = "check_emit_change_coverage.py" ]; then
    continue
  fi
  run_check "$GUARDRAIL_NAME" "$PYTHON_BIN" "$GUARDRAIL"
done
run_check "check_emit_change_coverage.py" "$PYTHON_BIN" scripts/check_emit_change_coverage.py

run_check "OpenAPI sync script" ./fichero-engine/scripts/sync_openapi_schema.sh
run_check "OpenAPI parity check" cmp -s \
  fichero-engine/tests/contracts/openapi.json \
  fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "✅ All validation checks passed"
  exit 0
else
  echo "❌ Validation finished with $FAILURES failing check(s)"
  exit 1
fi
