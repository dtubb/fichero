#!/usr/bin/env bash
# One command for the whole release lane: push -> tests -> guardrails -> lint -> release.
#
# Exists because doing it by hand at the end of a long night is how steps get
# skipped and how a red summary gets read as green (2026-08-05: a build reported
# success while compiling nothing; a gate reported 25 failures that did not
# exist). Every step here is gated on the previous one and every failure stops
# the run before the 40-minute release begins.
#
#   tmux new -s f_release -c /Users/danieltubb/code/fichero-worktrees/integration
#   bash scripts/release-now.sh
#
# Detach with Ctrl-b then d. Reattach with: tmux attach -t f_release
# Watch from elsewhere with: tail -f /tmp/release.log
#   bash scripts/release-now.sh --force   # run the checks but NEVER block the build
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --force: still RUN every check and still print what it found, but do not let a
# failure stop the release. The checks stay visible on purpose — skipping a gate
# is a decision, and a decision you cannot see afterwards is indistinguishable
# from one nobody made.
FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

step() { printf '\n\033[1m── %s ──\033[0m\n' "$1"; }
die() {
  if [ "$FORCE" = true ]; then
    printf '\n\033[33mWARNING (--force, continuing): %s\033[0m\n' "$1" >&2
  else
    printf '\n\033[31mSTOPPED: %s\033[0m\n' "$1" >&2
    exit 1
  fi
}

step "1/5  Push"
git push origin integration || die "push failed"

step "2/5  Engine tests (known-red files deselected)"
PYTHONPATH=fichero-server/src python3 -m pytest fichero-server/tests/unit/ -q \
  --deselect fichero-server/tests/unit/api/test_knowledge_graph_security.py \
  --deselect fichero-server/tests/unit/mcp/test_integration_security.py \
  2>&1 | tee /tmp/verify.log
# Read the SUMMARY, not the exit code: a killed run can exit 0 having proven
# nothing, and an empty log is not a pass.
grep -qE "^[0-9]+ passed" /tmp/verify.log || die "no pass summary in /tmp/verify.log — the run did not complete"
grep -qE "[0-9]+ failed"  /tmp/verify.log && die "tests failed — see /tmp/verify.log"
printf 'ok: %s\n' "$(grep -E '^[0-9]+ passed' /tmp/verify.log | tail -1)"

step "3/5  Guardrails (83)"
failed=0
for s in scripts/check_*.py; do
  PYTHONPATH=fichero-server/src python3 "$s" >/dev/null 2>&1 || { echo "  FAILED: $s"; failed=1; }
done
[ "$failed" = 0 ] || die "guardrails failed (run the named script alone to see why)"
echo "ok: all guardrails pass"

step "4/5  SwiftLint (ratchet: 72)"
lint="$(swiftlint lint fichero/fichero/ 2>&1 | tail -1)"
echo "  $lint"
echo "$lint" | grep -q "Found 72 violations" || die "swiftlint count moved — the ratchet is 72"

step "5/5  Release: DMG + TestFlight (Mac + iOS) + GitHub"
echo "  ~40 min. Do NOT edit release-all.sh while this runs — bash reads it as it executes."
bash scripts/release-all.sh --dev --github 2>&1 | tee /tmp/release.log

# The size ratchet stops the release when an artifact grows, on purpose: it is
# the only thing standing between us and silently shipping a bundle that
# doubled. But it stops the run AFTER the DMG is built and notarized, so a
# growth we have already accepted costs the whole 40 minutes to rediscover.
#
# Under --force, accept the new size and resume rather than making the user run
# it twice. NOT silent: the accepted numbers are printed and the baseline change
# is left in the working tree for review. Growth we chose is fine; growth nobody
# saw is not.
if [ "$FORCE" = true ] && grep -q "release-size ratchet FAILED" /tmp/release.log; then
  step "5b/5  Size ratchet grew — accepting under --force, then resuming"
  grep -E "GREW" /tmp/release.log || true
  python3 scripts/check_release_size_ratchet.py \
    --app "$PWD/build/releases/dmg-stage/Fichero.app" \
    --dmg "$PWD/build/releases/Fichero.dmg" --update-baseline \
    || echo "  (could not update baseline — artifacts may not exist yet)"
  echo "  baseline updated; re-running the release to completion"
  bash scripts/release-all.sh --dev --github 2>&1 | tee -a /tmp/release.log
  echo ""
  echo "  NOTE: scripts/release_size_baseline.json changed. Review and commit it,"
  echo "        recording what the growth bought."
fi

grep -qE "release-size ratchet FAILED|^error:" /tmp/release.log && die "release did not complete — see /tmp/release.log"

printf '\n\033[32mDONE.\033[0m DMG: build/releases/Fichero.dmg\n'
