#!/usr/bin/env bash
# Opt-in END-TO-END verification of the default workflows against a REAL
# on-device model (#4326). Gated like verify_perf.sh: deliberately NOT part
# of any gate — nothing runs this automatically.
#
# What it does (see scripts/verify_workflows.py for the full contract):
#   - seeds a disposable fixture library (seed_test_library.py --with-files)
#     under a throwaway FICHERO_BASE_PATH, so the run touches NO real data;
#   - boots uvicorn on loopback and runs every direct-runnable default
#     workflow through POST /api/workflow-execution/execute with the
#     on-device Apple provider (the #4325 keyless factory defaults);
#   - asserts status=completed (#4316), #4313 provenance fields on every
#     artifact the run wrote, and page_content for transcription workflows;
#   - prints one parseable "WORKFLOW-E2E | name=… | status=…" line per
#     workflow and exits 0 only when 0 failed. Workflows needing a
#     capability the host lacks report SKIP loudly, never silently pass.
#
# SCHEDULING (manager notes — also in agent-work/status/e2e-lane-notes.md):
#   - First run: post-release, in DAYLIGHT, on an idle machine (real model
#     calls; Apple Vision needs a GUI session — do not run headless/ssh).
#   - Serialize with xcodebuild and full pytest runs (one heavy job at a time).
#   - A red run names workflow + step + error per line → file one issue per
#     FAIL line. SKIP lines mean the HOST lacked a capability, not that the
#     workflow is healthy — schedule a run on hardware that has it.
#   - Companion per-tool smoke (opt-in pytest, mocked model for LLM tools):
#       FICHERO_WORKFLOW_E2E=1 PYTHONPATH=fichero-server/src \
#         .venv/bin/python -m pytest \
#         fichero-server/tests/integration/test_workflow_tool_smoke.py -q
#
# Usage:
#   scripts/verify_workflows.sh                      # full sweep (~25 min budget)
#   scripts/verify_workflows.sh --only 'Catalogue'   # subset by name regex
#   scripts/verify_workflows.sh --list               # print plan, run nothing
#   scripts/verify_workflows.sh --timeout 300 --budget 1500 --keep
# Extra arguments pass straight through to scripts/verify_workflows.py.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

PYTHON_BIN="${FICHERO_PYTHON_BIN:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "❌ No usable interpreter at '$PYTHON_BIN'." >&2
  echo "   Activate the venv or set FICHERO_PYTHON_BIN=/path/to/.venv/bin/python" >&2
  exit 2
fi

# One heavy job at a time on this box (see verify_perf.sh for history).
if pgrep -f xcodebuild >/dev/null 2>&1; then
  echo "⚠️  An xcodebuild is running. This lane makes real model calls and will" >&2
  echo "   compete with it; consider waiting. Continuing in 5s (Ctrl-C to abort)." >&2
  sleep 5
fi

echo "── default-workflow E2E lane (real on-device model, #4326) ──"
FICHERO_PYTHON_BIN="$PYTHON_BIN" "$PYTHON_BIN" scripts/verify_workflows.py "$@"
status=$?

if [ "$status" -eq 0 ]; then
  echo "✅ workflow E2E lane passed"
else
  echo "❌ workflow E2E lane failed (exit $status)"
fi
exit "$status"
