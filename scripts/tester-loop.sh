#!/usr/bin/env bash
# tester-loop.sh — programmatic QA loop. Verify the latest merged main, file a
# tracked issue per failure. NO LLM: verify_all.sh produces the report,
# verify_to_issues.sh --apply files/de-dupes the issues. Deterministic + cheap.
#
#   bash scripts/tester-loop.sh            # loop forever (Ctrl-C to stop)
#   TESTER_TIER=--standard bash …          # backend-only (default --full)
#   TESTER_SLEEP=600 bash …                # seconds between runs (default 300)
#
# Build-lock aware: never runs while another xcodebuild is active (one build
# machine-wide, slow machine) so it can't collide with the integrator's gates.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

TIER="${TESTER_TIER:---full}"
SLEEP="${TESTER_SLEEP:-300}"

while true; do
  git fetch origin -q && git reset --hard origin/main -q

  # build-lock: wait out any active build (integrator gate / another verify)
  while pgrep -x xcodebuild >/dev/null 2>&1; do sleep 30; done

  echo "=== verify $(date '+%H:%M:%S') ($TIER) ==="
  bash scripts/verify_all.sh "$TIER" --json 2>&1 | tail -20 || true   # always writes build/verify_all_report.json

  # file/de-dupe issues from the report (no-op when everything passed)
  bash scripts/verify_to_issues.sh --apply 2>&1 | tail -20 || true

  # signal the manager (best-effort)
  if [ -f build/verify_all_needs_fixing.json ]; then
    bash scripts/notify_manager.sh "verify FAILED — filed issues (build/verify_all_needs_fixing.json)" 2>/dev/null || true
  else
    bash scripts/notify_manager.sh "verify passed ($TIER, $(date +%H:%M))" 2>/dev/null || true
  fi

  sleep "$SLEEP"
done
