#!/usr/bin/env bash
# Simulator UI runner (#4782, #4771): the Mac starts the seeded harness engine, the simulator run
# dials its socket. A simulator runner cannot launch a host process, so this script does it.
# Usage: scripts/run_ios_ui_sim.sh [destination]   (default: iPhone 17 Pro, iOS 27 simulator)
# Builds one at a time; run only when no suite is running anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:-platform=iOS Simulator,name=iPhone 17 Pro}"
PY="${FICHERO_VENV:-.venv}/bin/python"
SOCK="/tmp/fichero-ios-ui-$$.sock"
READY="$(mktemp)"
"$PY" fichero-server/scripts/test_engine_harness.py --socket "$SOCK" --seed-mode full >"$READY" &
ENGINE=$!
trap 'kill "$ENGINE" 2>/dev/null || true; rm -f "$SOCK" "$READY"' EXIT
for _ in $(seq 1 120); do
  [ -s "$READY" ] && break
  kill -0 "$ENGINE" 2>/dev/null || { echo "harness engine exited before ready" >&2; exit 3; }
  sleep 1
done
[ -s "$READY" ] || { echo "harness engine never printed its ready line" >&2; exit 3; }
TEST_RUNNER_FICHERO_FORCE_UDS_PATH="$SOCK" xcodebuild test \
  -project fichero/fichero.xcodeproj -scheme "Fichero (Dev Local)" \
  -destination "$DEST" -testPlan fichero-ui-ios \
  CODE_SIGNING_ALLOWED=NO -skipPackagePluginValidation
