#!/usr/bin/env bash
# Run the engine PERFORMANCE suite (fichero-engine/tests/perf).
#
# This is deliberately NOT part of any gate. The gates cover tests/unit/ and
# tests/contracts/; nothing runs tests/perf/ automatically, so without this
# script it is only ever reached by typing the whole-tree `pytest
# fichero-engine/tests` form — a ~70-minute invocation most people hit by
# accident (#4174).
#
# WHY it is excluded: measured 2026-07-28 on a full-tree run (4219s total),
# two perf tests alone account for 3089s — 73% of the entire suite:
#     1612s  test_entity_list_perf.py::test_list_entities_full_scale
#     1477s  test_entity_list_perf.py::test_list_entities_doc_scoped_scale
# Everything outside tests/perf/ drops under 12s per test.
#
# These tests are SLOW, NOT HUNG. Each takes ~25 minutes and, under -q with no
# progress output, has previously been mistaken for a hang (#4039). -s is on by
# default here so their measurements stream and you can see progress.
#
# Usage:
#   scripts/verify_perf.sh              # whole perf suite
#   scripts/verify_perf.sh -k entity    # a subset
# Any extra arguments are passed straight through to pytest.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

PYTHON_BIN="${FICHERO_PYTHON_BIN:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "❌ No usable interpreter at '$PYTHON_BIN'." >&2
  echo "   Activate the venv or set FICHERO_PYTHON_BIN=/path/to/.venv/bin/python" >&2
  exit 2
fi

# One xcodebuild or full pytest at a time on this box: concurrent heavy runs
# have pushed load past 200 and had processes killed by the OS, which surfaces
# as a red gate that looks like a code bug.
if pgrep -f xcodebuild >/dev/null 2>&1; then
  echo "⚠️  An xcodebuild is running. The perf suite takes ~50 minutes and will" >&2
  echo "   compete with it; consider waiting. Continuing in 5s (Ctrl-C to abort)." >&2
  sleep 5
fi

echo "── engine perf suite (fichero-engine/tests/perf) ──"
echo "   Expect ~50 minutes; the two entity-list tests are ~25 minutes EACH."
echo "   Slow is normal here — see #4039 before reporting a hang."

PYTHONPATH="fichero-engine/src" "$PYTHON_BIN" -m pytest \
  fichero-engine/tests/perf/ -q -s -rf "$@"
status=$?

if [ "$status" -eq 0 ]; then
  echo "✅ perf suite passed"
else
  echo "❌ perf suite failed (exit $status)"
fi
exit "$status"
