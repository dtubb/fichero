#!/usr/bin/env bash
# One command to verify the whole product: Swift lint + the full Xcode test run
# (which compiles the app = frontend build, runs Swift tests + the live
# AppEngineContractTests, and runs CrossLanguageGateTests → verify_python.sh,
# i.e. the entire Python side). Same coverage as ⌘U.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

fail=0

echo "── swiftlint ──"
if swiftlint lint --quiet fichero/fichero/; then echo "✅ swiftlint"; else echo "❌ swiftlint"; fail=1; fi

# Architecture guardrails — cheap, no GUI, fail-fast BEFORE the heavy xcodebuild
# test. These catch exactly the regressions verify_all exists to catch: a view
# talking to the backend instead of an @Observable store (hand-rolled URLs /
# non-observers), and raw DuckDB/SQL leaking out of the db.py persistence layer.
# Manager-run only; workers never run verify_all (the xcodebuild test below
# spawns the app + engine — running it from several worktrees blows up RAM).
echo "── architecture guardrails (view→store, db.py access) ──"
if python3 scripts/check_view_endpoint_access.py; then echo "✅ view→store guardrail"; else echo "❌ view→store guardrail"; fail=1; fi
if PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/test_db_access_guardrail.py >/dev/null 2>&1; then echo "✅ db-access guardrail"; else echo "❌ db-access guardrail"; fail=1; fi

echo "── xcodebuild test (Swift suite + CrossLanguageGate → Python gate) ──"
if xcodebuild test \
    -project fichero/fichero.xcodeproj \
    -scheme Fichero \
    -destination 'platform=macOS' \
    -skipPackagePluginValidation \
    -resultBundlePath "$(mktemp -d)/verify.xcresult"; then
  echo "✅ xcodebuild test"
else
  echo "❌ xcodebuild test"; fail=1
fi

echo
if [ "$fail" = 0 ]; then echo "✅✅ verify_all: ALL PASS"; else echo "❌❌ verify_all: FAILURES ABOVE"; fi
exit "$fail"
