#!/usr/bin/env bash
# Single source of truth for the Python side of the unified verification gate:
# lint + unit tests + GET-contract walk + backend start-smoke + CLI smoke + the
# live CLI<->engine contract test. Exits non-zero if any leg fails.
# Invoked by CrossLanguageGateTests.swift (so ⌘U runs it) and, later, the autoloop.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
export PYTHONPATH="fichero-engine/src"
PY=".venv/bin/python"
PYTEST=".venv/bin/pytest"
RUFF=".venv/bin/ruff"
UVICORN=".venv/bin/uvicorn"

fail=0
run() {  # run "<label>" <cmd...>
  local label="$1"; shift
  echo "── $label ──"
  if "$@"; then echo "✅ $label"; else echo "❌ $label"; fail=1; fi
}

# 1. Lint (ruff == "pylint"). Canonical scope is src/ only (per CLAUDE.md); the
# tests/ and scripts/ trees carry pre-existing lint debt and are out of scope.
run "ruff" "$RUFF" check fichero-engine/src/

# 2. Backend unit tests (includes the mocked CLI unit tests).
#    `-k "not embedding"` skips tests that need an unavailable fastembed model
#    (env limitation, not a code bug). Drop the filter if the model is present.
run "backend unit" "$PYTEST" fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived -q -k "not embedding"

# 3. GET contract walk (every list endpoint serializes against its response_model).
run "contract walk" "$PYTEST" fichero-engine/tests/integration/test_contract_endpoint_walk.py -q

# 4. Backend start-smoke: boot the engine, confirm it serves /health, tear down.
echo "── backend start-smoke ──"
SMOKE_PORT=8799
FICHERO_DISABLE_AUTH=1 FICHERO_FEATURE_TIER=dev FICHERO_SKIP_DEFAULT_WORKFLOWS=1 \
  FICHERO_BASE_PATH="$(mktemp -d)" FICHERO_PARENT_PID=$$ \
  "$UVICORN" fichero.api.main:app --host 127.0.0.1 --port "$SMOKE_PORT" >/dev/null 2>&1 &
SMOKE_PID=$!
ok=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 0.5
done
kill "$SMOKE_PID" 2>/dev/null; wait "$SMOKE_PID" 2>/dev/null
if [ "$ok" = 1 ]; then echo "✅ backend start-smoke"; else echo "❌ backend start-smoke"; fail=1; fi

# 5. CLI smoke: the CLI imports and its entrypoint runs.
run "cli import" "$PY" -c "import fichero.cli"
run "cli --help" "$PY" -m fichero --help

# 6. Live CLI<->engine contract test.
run "cli contract" "$PYTEST" fichero-engine/tests/integration/test_cli_engine_contract.py -q

# 7. OpenAPI freshness — confirm committed schema matches the live backend and that
#    the Swift client copy is in sync. Re-exports the schema (Python only, no swift build)
#    and diffs against the committed files; restores the working tree on mismatch so the
#    gate never leaves dirty files behind.
echo "── openapi freshness ──"
PYTHONPATH=fichero-engine/src FICHERO_FEATURE_TIER=dev "$PY" \
  fichero-engine/scripts/export_openapi_schema.py >/dev/null 2>&1
if ! git diff --quiet -- fichero-engine/tests/contracts/openapi.json \
                          fichero-engine/tests/contracts/endpoints.json; then
  echo "❌ openapi freshness — backend routes changed; run ./fichero-engine/scripts/sync_openapi_schema.sh and commit"
  git checkout -- fichero-engine/tests/contracts/openapi.json \
                  fichero-engine/tests/contracts/endpoints.json 2>/dev/null || true
  fail=1
elif ! cmp -s fichero-engine/tests/contracts/openapi.json \
              fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json; then
  echo "❌ openapi freshness — openapi.json updated but Swift client not synced; run ./fichero-engine/scripts/sync_openapi_schema.sh and commit"
  fail=1
else
  echo "✅ openapi freshness"
fi

# 8. Feature-tier freshness — regenerate into a temp copy and confirm the
#    committed feature-tier artifacts still match features.yaml.
run "feature tier freshness" "$PY" scripts/check_features_freshness.py

echo
if [ "$fail" = 0 ]; then echo "✅✅ verify_python: ALL PASS"; else echo "❌❌ verify_python: FAILURES ABOVE"; fi
exit "$fail"
