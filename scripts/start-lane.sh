#!/usr/bin/env bash
# Start a Claude lane with its ground verified first (#5048).
#
# Everything that cost hours on 2026-09-26 was an unverified assumption about the
# environment, not a mistake in reasoning: a revoked token, a closed Xcode reported
# as a broken MCP server, sixty stale LaunchServices registrations behind a
# "HOST NEVER STARTED", a drifted venv behind a refused OpenAPI regeneration.
# Each was cheap to check and expensive to diagnose.
#
# It REPORTS; it does not repair. Repair is a decision — reinstalling an editable
# package changes the contract version, which is a release decision, not housekeeping
# (ruled 2026-09-26). Exit code is 0 when nothing blocks, 1 when something does.
#
# Usage:
#   scripts/start-lane.sh              # preflight, then exec claude
#   scripts/start-lane.sh --check      # preflight only, no claude
#   scripts/start-lane.sh --self-test  # prove each check can FAIL
#   scripts/start-lane.sh -- <args>    # pass args through to claude
#
# Spec: docs/contributor_manual/specs/harness/version-and-contract-integrity.md
#       behaviour `lane.preflight-deterministic`

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLOCKERS=0
NOTES=0

ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$1"; NOTES=$((NOTES+1)); }
bad()   { printf '  \033[31m✗\033[0m %s\n' "$1"; BLOCKERS=$((BLOCKERS+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# A check that cannot read its input FAILS. It never reports success on data it did
# not see — a preflight that says "all clear" because it read nothing is worse than
# no preflight at all (AGENTS.md rule 0).
require_file() {
  [ -r "$1" ] && return 0
  bad "cannot read $1 — check is BLIND, not passing"
  return 1
}

check_worktree() {
  head_ "Worktree"
  cd "$REPO_ROOT" || { bad "cannot enter $REPO_ROOT"; return; }
  local branch dirty
  branch="$(git branch --show-current 2>/dev/null)" || { bad "not a git repository"; return; }
  ok "$REPO_ROOT on '$branch'"
  dirty="$(git status --porcelain 2>/dev/null | grep -vc '^??' || true)"
  [ "${dirty:-0}" -gt 0 ] && warn "$dirty tracked files modified — know why before committing"
  return 0
}

# The canonical venv is editable-installed against the MAIN checkout and drifts.
# Name the one that can actually run the OpenAPI sync, so nobody reaches for `sed`
# on info.version when the regression guard (#4199) refuses.
check_venv() {
  head_ "Python environment"
  local best="" best_ver="" pyproject_ver="" v p
  require_file "$REPO_ROOT/fichero-server/pyproject.toml" || return
  pyproject_ver="$(grep -m1 '^version' "$REPO_ROOT/fichero-server/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')"
  [ -n "$pyproject_ver" ] || { bad "cannot parse version from pyproject.toml"; return; }
  ok "pyproject.toml declares $pyproject_ver"

  # The canonical venv is editable-installed against the MAIN checkout, not a
  # worktree — derive it from git rather than hard-coding a path, so this works
  # for anyone whose checkout is not at ~/code/fichero.
  local main_checkout
  main_checkout="$(cd "$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
  for p in "$REPO_ROOT/fichero-server/.venv" "$REPO_ROOT/.venv" "${main_checkout:-/nonexistent}/.venv"; do
    [ -x "$p/bin/python" ] || continue
    v="$("$p/bin/python" -c 'import importlib.metadata as m; print(m.version("fichero-server"))' 2>/dev/null)"
    [ -n "$v" ] || { warn "$p — engine not installed"; continue; }
    printf '    %s → %s\n' "$p" "$v"
    # Prefer a venv whose metadata MATCHES pyproject — picking merely the first
    # one found is how a stale interpreter gets exported, which is what makes
    # sync_openapi_schema.sh refuse and tempts someone to sed info.version
    # instead (#5046). Fall back to the first only if none matches.
    if [ "$v" = "$pyproject_ver" ] && [ "$best_ver" != "$pyproject_ver" ]; then
      best="$p"; best_ver="$v"
    elif [ -z "$best" ]; then
      best="$p"; best_ver="$v"
    fi
  done

  if [ -z "$best" ]; then
    bad "no venv holds the engine — the OpenAPI sync cannot run (#5043)"
    return
  fi
  export FICHERO_PYTHON_BIN="$best/bin/python"
  export PYTHONPATH="$REPO_ROOT/fichero-server/src"
  ok "FICHERO_PYTHON_BIN → $best ($best_ver)"
  ok "PYTHONPATH → fichero-server/src"
  [ "$best_ver" != "$pyproject_ver" ] &&
    warn "no venv holds the CURRENT install ($best_ver vs $pyproject_ver) — #5043"
  return 0
}

# Ruled 2026-09-26: info.version must ALWAYS equal pyproject.toml. It does not today
# (#5046) — the contract froze at 2026.9.8 while releases shipped past it.
check_contract() {
  head_ "OpenAPI contract"
  local f="$REPO_ROOT/fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"
  require_file "$f" || return
  local cv pv
  cv="$(python3 -c "import json;print(json.load(open('$f'))['info']['version'])" 2>/dev/null)"
  pv="$(grep -m1 '^version' "$REPO_ROOT/fichero-server/pyproject.toml" 2>/dev/null | sed 's/.*"\(.*\)".*/\1/')"
  [ -n "$cv" ] && [ -n "$pv" ] || { bad "cannot read both versions — check is BLIND"; return; }
  if [ "$cv" = "$pv" ]; then
    ok "contract $cv matches the code"
  else
    warn "contract $cv lags the code $pv — #5046 (regenerate, NEVER sed info.version)"
  fi
  return 0
}

# Without Xcode.app running there is NO working path to app-hosted Swift tests on
# this machine: the CLI gate aborts HOST NEVER STARTED, and the xcode MCP reports
# CONNECTION_CLOSED, which reads like a broken server rather than a closed editor.
check_swift_path() {
  head_ "Swift test path"
  if pgrep -x Xcode >/dev/null 2>&1; then
    ok "Xcode.app running — the xcode MCP can run app-hosted tests"
    ok "remember: switch to scheme 'Fichero (Dev Local)' before RunSomeTests"
  else
    bad "Xcode.app NOT running — app-hosted Swift tests cannot run at all"
    printf '      Python and edits still work; say Swift is UNVERIFIED rather than implying otherwise.\n'
  fi
  return 0
}

# Every build product, DMG staging dir, gate snapshot and mounted .dmg registers
# ANOTHER Fichero.app under the same bundle id. Once dozens point at paths that no
# longer exist, the test host fails to launch with `childPID > 0`.
check_test_host() {
  head_ "Test-host saboteurs"
  local ls_bin="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [ -x "$ls_bin" ]; then
    local stale=0 p
    while IFS= read -r p; do
      [ -n "$p" ] && [ ! -d "$p" ] && stale=$((stale+1))
    done < <("$ls_bin" -dump 2>/dev/null | grep -i '^\s*path:.*Fichero\.app' | sed 's/.*path: *//;s/ (0x.*//' | sort -u)
    if [ "$stale" -gt 5 ]; then
      warn "$stale stale Fichero.app registrations — can break the test host (lsregister -u <path>)"
    else
      ok "$stale stale Fichero.app registrations"
    fi
  else
    warn "lsregister not found — cannot check registrations"
  fi
  local engines
  engines="$(pgrep -fc 'Fichero Server.app/Contents/MacOS/Fichero Server' 2>/dev/null || echo 0)"
  [ "${engines:-0}" -gt 0 ] && warn "$engines leftover engine process(es) running"
  return 0
}

# Each check must FAIL on input it cannot read, not pass blind. Asserted on the
# checks' OUTPUT, not on $BLOCKERS: a check called inside command substitution runs
# in a SUBSHELL, so its counter increments never reach here — reading the counter
# would make this self-test pass no matter what the check did.
self_test() {
  head_ "Self-test — every check must be able to FAIL"
  local fails=0 out

  out="$(require_file "/nonexistent/$$" 2>&1)"
  case "$out" in *BLIND*) printf '  ✓ require_file fails loudly on a missing file\n';;
    *) printf '  ✗ require_file did not report BLIND\n'; fails=1;; esac

  out="$(REPO_ROOT=/nonexistent check_worktree 2>&1)"
  case "$out" in *"cannot enter"*|*"not a git repository"*) printf '  ✓ check_worktree fails on a missing repo\n';;
    *) printf '  ✗ check_worktree did not fail on a missing repo\n'; fails=1;; esac

  local tmp; tmp="$(mktemp -d)"; mkdir -p "$tmp/fichero-server"
  printf 'version = "9999.1.1"\n' > "$tmp/fichero-server/pyproject.toml"
  out="$(REPO_ROOT="$tmp" check_contract 2>&1)"
  case "$out" in *BLIND*) printf '  ✓ check_contract fails when the contract is unreadable\n';;
    *) printf '  ✗ check_contract did not report BLIND on a missing contract\n'; fails=1;; esac
  rm -rf "$tmp"

  if [ "$fails" -eq 0 ]; then
    printf '  \033[32mself-test passed\033[0m — checks fail on bad input rather than passing blind\n'
    return 0
  fi
  printf '  \033[31mself-test FAILED\033[0m\n'
  return 1
}

case "${1:-}" in
  --self-test) self_test; exit $? ;;
esac

printf '\033[1mLane preflight\033[0m — reports, never repairs (#5048)\n'
check_worktree
check_venv
check_contract
check_swift_path
check_test_host

head_ "Summary"
if [ "$BLOCKERS" -gt 0 ]; then
  printf '  \033[31m%d blocker(s)\033[0m, %d note(s)\n' "$BLOCKERS" "$NOTES"
else
  printf '  \033[32mno blockers\033[0m, %d note(s)\n' "$NOTES"
fi

[ "${1:-}" = "--check" ] && exit $(( BLOCKERS > 0 ? 1 : 0 ))

[ "${1:-}" = "--" ] && shift
printf '\nStarting claude...\n\n'
exec claude "$@"
