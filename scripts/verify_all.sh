#!/usr/bin/env bash
# Tiered verification entrypoint.
#
#   --fast      Swift lint + cheap guardrails + version-date + OpenAPI model sync
#   --standard  fast + backend unit tests
#   --full      standard + requested platform legs; defaults to both macOS and
#               the generic iOS Simulator compile gate when no platform flags
#               are given
#   VERIFY_ALL_MACOS=1 / VERIFY_ALL_IOS=1 can request platform legs without
#   changing the tier.
#
# Default is --fast so tooling workers can run the cheap gate without kicking off
# the app build/test suite. Managers/integrators own --full.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

# The one aggregated gate: guardrails + engine + Swift unit (split phases) +
# hermetic UI + transport matrix + coverage, one summary table, exit 0 =
# releasable. `verify_all.sh --standard|--fast` remain the tier entrypoints.
if [[ "${1:-}" == "--gate-all" ]]; then
  exec scripts/gate verify-all
fi

# #4251: every verify run goes THROUGH the gate harness — one global lock, the
# memory watchdog, and per-run timeouts — so a verify can never stack on top
# of another build/test run. GATE_LOCK_HELD marks a process already under the
# gate (including `gate verify-all` legs); FICHERO_GATE=1 or
# VERIFY_ALL_NO_GATE=1 bypass explicitly (debugging only).
if [[ -z "${GATE_LOCK_HELD:-}" && -z "${FICHERO_GATE:-}" \
      && -z "${VERIFY_ALL_NO_GATE:-}" && -x scripts/gate ]]; then
  exec scripts/gate wrap -- "$0" "$@"
fi

tier="fast"
run_macos=0
run_ios=0
selfcheck=0
json_requested=0
file_issues=0
show_help() {
  cat <<'EOF'
Usage:
  scripts/verify_all.sh [--fast|--standard|--full] [--macos] [--ios] [--json] [--self-check]

Tiers:
  --fast      swiftlint + ruff + scripts/check_*.py + check_version_date.sh + OpenAPI model sync
  --standard  fast + backend pytest unit tests
  --full      standard + requested platform legs; defaults to both when no
              platform flags are given
  --gate-all  delegate to `scripts/gate verify-all`: guardrails + engine +
              Swift unit (split phases) + hermetic UI + transport matrix +
              coverage, serialized + watchdogged, one summary table (#4251)

Every invocation is automatically wrapped in `scripts/gate` (global lock +
memory watchdog); set VERIFY_ALL_NO_GATE=1 to bypass for debugging.

Platforms:
  --macos     run only the macOS Xcode build/test leg
  --ios       run only the generic iOS Simulator compile gate

Environment overrides:
  VERIFY_ALL_MACOS=1  request the macOS Xcode build/test leg
  VERIFY_ALL_IOS=1    request the generic iOS Simulator compile gate

Reporting:
  --json        always also writes a machine-readable failure report to
                build/verify_all_report.json (the file is written regardless;
                this flag is accepted for explicitness)
  --self-check  run an internal pass+fail probe, assert the JSON report has
                exactly one failure record, then exit with the aggregated status
  --file-issues on failure, invoke scripts/verify_to_issues.sh --apply to file
                de-duped GitHub issues into the right milestones, write the
                manager-flag build/verify_all_needs_fixing.json, and print a
                MANAGER-ACTION line. Default OFF (report only).

Default: --fast

Manager examples:
  scripts/verify_all.sh --standard --macos --ios
  scripts/verify_all.sh --full --macos
  scripts/verify_all.sh --full --ios
EOF
}

is_truthy() {
  case "$1" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

for arg in "$@"; do
  case "$arg" in
    --fast)
      tier="fast"
      ;;
    --standard)
      tier="standard"
      ;;
    --full)
      tier="full"
      ;;
    --macos)
      run_macos=1
      ;;
    --ios)
      run_ios=1
      ;;
    --json)
      json_requested=1
      ;;
    --self-check)
      selfcheck=1
      ;;
    --file-issues)
      file_issues=1
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown verify tier: $arg" >&2
      echo "Usage: scripts/verify_all.sh [--fast|--standard|--full] [--macos] [--ios] [VERIFY_ALL_MACOS=1] [VERIFY_ALL_IOS=1]" >&2
      exit 2
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  tier="fast"
fi

if is_truthy "${VERIFY_ALL_MACOS:-}"; then
  run_macos=1
fi
if is_truthy "${VERIFY_ALL_IOS:-}"; then
  run_ios=1
fi

if [[ "$tier" == "full" && "$run_macos" -eq 0 && "$run_ios" -eq 0 ]]; then
  run_macos=1
  run_ios=1
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
else
  PYTHON_BIN="$(scripts/find_project_python.sh .)" || exit 2
fi

PYTEST_CMD=("${PYTHON_BIN}" -m pytest)
if [[ -x ".venv/bin/pytest" ]]; then
  PYTEST_CMD=(".venv/bin/pytest")
fi

RUFF_CMD=("${PYTHON_BIN}" -m ruff)
if ! "${PYTHON_BIN}" -c "import ruff" >/dev/null 2>&1; then
  RUFF_CMD=(ruff)
fi

fail=0
FAILED_CHECKS=()

# --- Machine-readable failure report (build/verify_all_report.json) ----------
# Each failing check appends a staged record; write_report() serialises them to
# JSON at the end. build/ is gitignored. This is purely additive — the human
# "FAILED CHECKS" block below is untouched.
REPORT_JSON="build/verify_all_report.json"
REPORT_STAGING="$(mktemp -d)"
REPORT_COUNT=0
trap 'rm -rf "${REPORT_STAGING}"' EXIT

# Map a human check label to a stable category used for milestone routing.
categorize_label() {
  local label="$1"
  case "$label" in
    swiftlint*) echo "swift-lint" ;;
    *ruff*) echo "python-lint" ;;
    *OpenAPI*) echo "contract" ;;
    *pytest*) echo "test" ;;
    *xcodebuild*) echo "build" ;;
    version-date|check_*.py|check_*) echo "guardrail" ;;
    *) echo "other" ;;
  esac
}

# Stage one failure record. Args: label, output-file, then the command argv.
record_failure() {
  local label="$1"
  local outfile="$2"
  shift 2
  local idx
  idx="$(printf '%04d' "$REPORT_COUNT")"
  local dir="${REPORT_STAGING}/${idx}"
  mkdir -p "$dir"
  printf '%s' "$label" >"$dir/label"
  printf '%s' "$(categorize_label "$label")" >"$dir/category"
  printf '%s' "$tier" >"$dir/tier"
  printf '%s' "$*" >"$dir/command"
  if [[ -n "$outfile" && -f "$outfile" ]]; then
    tail -n 40 "$outfile" >"$dir/output_tail" 2>/dev/null || true
  else
    : >"$dir/output_tail"
  fi
  # For the pytest leg, parse failing test node IDs from the summary lines.
  case "$label" in
    *pytest*)
      if [[ -n "$outfile" && -f "$outfile" ]]; then
        grep -E '^FAILED ' "$outfile" \
          | sed -E 's/^FAILED ([^ ]+).*/\1/' >"$dir/failing_tests" || true
      fi
      ;;
  esac
  REPORT_COUNT=$((REPORT_COUNT + 1))
}

# Serialise all staged records to REPORT_JSON. Pure python3 (stdlib only) for
# safe escaping; falls back to a minimal valid file if python3 is unavailable.
write_report() {
  mkdir -p "$(dirname "$REPORT_JSON")"
  if REPORT_STAGING="$REPORT_STAGING" REPORT_JSON="$REPORT_JSON" TIER="$tier" \
      "${PYTHON_BIN}" - <<'PY' 2>/dev/null
import glob
import json
import os

staging = os.environ["REPORT_STAGING"]
out = os.environ["REPORT_JSON"]


def read(path):
    try:
        with open(path) as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


records = []
for d in sorted(glob.glob(os.path.join(staging, "*"))):
    if not os.path.isdir(d):
        continue
    rec = {
        "label": read(os.path.join(d, "label")),
        "category": read(os.path.join(d, "category")),
        "tier": read(os.path.join(d, "tier")),
        "command": read(os.path.join(d, "command")),
        "output_tail": read(os.path.join(d, "output_tail")),
    }
    ft = os.path.join(d, "failing_tests")
    if os.path.exists(ft):
        rec["failing_tests"] = [
            line for line in read(ft).splitlines() if line.strip()
        ]
    records.append(rec)

report = {"tier": os.environ.get("TIER", ""), "failed": len(records), "checks": records}
with open(out, "w") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
PY
  then
    :
  else
    # Minimal fallback so the path always exists and is valid JSON.
    printf '{"tier":"%s","failed":%d,"checks":[]}\n' "$tier" "$REPORT_COUNT" >"$REPORT_JSON"
  fi
  # Render a scannable HTML dashboard next to the JSON so failures are visible
  # ("a place you can see what is failing", #3163). Best-effort — a render
  # hiccup must never fail the verify run itself.
  "${PYTHON_BIN}" scripts/render_verify_report.py "$REPORT_JSON" "${REPORT_JSON%.json}.html" >/dev/null 2>&1 || true
}

XCODE_PROJECT="fichero/fichero.xcodeproj"
# The scheme/test rework split the old single "Fichero" scheme into
# per-platform/per-channel schemes (there is no bare "Fichero" any more), so
# the macOS and iOS build legs must target different schemes.
XCODE_SCHEME_MACOS="Fichero (Dev Local)"
XCODE_SCHEME_IOS="Fichero (Dev Local iOS)"
IOS_SIMULATOR_DESTINATION="generic/platform=iOS Simulator"
VERIFY_ALL_DERIVED_ROOT="${VERIFY_ALL_DERIVED_ROOT:-build/verify-all-derived}"

run_xcode_build() {
  local label="$1"
  shift
  run_check "$label" xcodebuild "$@" -skipPackagePluginValidation build
}

run_xcode_test() {
  local label="$1"
  shift
  run_check "$label" xcodebuild "$@" -skipPackagePluginValidation test
}

skip_check() {
  local label="$1"
  local reason="$2"
  echo "-- ${label} --"
  echo "SKIP ${label} (${reason})"
}

run_check() {
  local label="$1"
  shift
  echo "-- ${label} --"
  # Capture combined output so we can tail it into the JSON report on failure,
  # while still streaming it to the terminal unchanged (tee passthrough).
  local outfile
  outfile="$(mktemp)"
  if "$@" 2>&1 | tee "$outfile"; then
    echo "PASS ${label}"
  else
    echo "FAIL ${label}"
    fail=1
    FAILED_CHECKS+=("${label}")
    record_failure "$label" "$outfile" "$@"
  fi
  rm -f "$outfile"
}

run_fast() {
  echo "verify_all tier: fast"

  run_check "swiftlint" swiftlint lint --quiet --cache-path .swiftlint-cache fichero/fichero/

  run_check "backend ruff" env PYTHONPATH=fichero-server/src:fichero-cli/src:fichero-mcp/src \
    "${RUFF_CMD[@]}" check fichero-server/src/ fichero-cli/src/ fichero-mcp/src/

  echo "-- architecture and tooling guardrails --"
  local guardrail
  for guardrail in scripts/check_*.py; do
    if [[ "$(basename "$guardrail")" == "check_unmerged_work.py" || "$(basename "$guardrail")" == "check_emit_change_coverage.py" ]]; then
      continue
    fi
    run_check "$(basename "$guardrail")" "${PYTHON_BIN}" "$guardrail"
  done
  run_check "check_emit_change_coverage.py" "${PYTHON_BIN}" scripts/check_emit_change_coverage.py

  run_check "version-date" scripts/check_version_date.sh

  run_check "OpenAPI model sync" env PYTHONPATH=fichero-server/src:fichero-cli/src:fichero-mcp/src \
    "${PYTHON_BIN}" fichero-server/scripts/validate_model_sync.py
}

run_standard() {
  echo "verify_all tier: standard"
  run_fast

  # -rf emits a "FAILED <node_id>" line per failure in the short summary so the
  # JSON report can list failing test node IDs (parsed in record_failure).
  run_check "backend pytest unit tests" env PYTHONPATH=fichero-server/src:fichero-cli/src:fichero-mcp/src \
    "${PYTEST_CMD[@]}" -rf fichero-server/tests/unit/ fichero-cli/tests/ fichero-mcp/tests/ \
    --ignore=fichero-server/tests/unit/_archived

  # Contract tests (OpenAPI surface, UI-wiring coverage, docs coverage) — these
  # guard against exactly the kind of drift unit-only gating missed (#3163): a
  # new endpoint added without a SwiftUI caller / docs / allowlist entry.
  run_check "backend pytest contract tests" env PYTHONPATH=fichero-server/src:fichero-cli/src:fichero-mcp/src \
    "${PYTEST_CMD[@]}" -rf fichero-server/tests/contracts/

  # State the exclusion out loud: a gate that silently stops covering a quarter
  # of the suite is how coverage rots (#4174). tests/perf has never been in any
  # gate, so this documents reality rather than changing it.
  echo "ℹ️  Not covered: fichero-server/tests/perf (~50 min, 73% of a whole-tree run) — scripts/verify_perf.sh"
}

run_platform_checks() {
  echo "verify_all platform legs: macOS=${run_macos} iOS=${run_ios}"

  if [[ "$run_macos" -eq 1 ]]; then
    run_xcode_build "xcodebuild macOS build" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME_MACOS}" \
      -destination 'platform=macOS'

    run_xcode_test "xcodebuild macOS test (FicheroTests test plan)" \
      -project "${XCODE_PROJECT}" \
      -scheme "FicheroTests" \
      -destination 'platform=macOS' \
      -resultBundlePath "$(mktemp -d)/verify.xcresult"

    run_xcode_test "xcodebuild macOS UI smoke tests" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME_MACOS}" \
      -testPlan "fichero" \
      -destination 'platform=macOS' \
      -resultBundlePath "$(mktemp -d)/verify-ui.xcresult"

    # Embedded-launch UX test — actually LAUNCHES the embedded app and proves it
    # connects + reaches a live library with no failure splash (the #3968 gap that
    # let the "library then Can't-Authenticate" bug ship). Opt-in (VERIFY_ALL_EMBEDDED=1)
    # because it briefcase-builds the ~1GB engine (~10 min) and needs a GUI session
    # + a one-time Accessibility grant. Reuse a fresh bundle with FICHERO_REUSE_ENGINE_BUNDLE=1.
    if is_truthy "${VERIFY_ALL_EMBEDDED:-}"; then
      run_check "embedded launch UX (connects + reaches library)" \
        scripts/verify_embedded_launch.sh
    else
      skip_check "embedded launch UX (connects + reaches library)" \
        "set VERIFY_ALL_EMBEDDED=1 (briefcase build + GUI session required)"
    fi
  fi

  if [[ "$run_ios" -eq 1 ]]; then
    run_xcode_build "xcodebuild iOS Simulator compile gate" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME_IOS}" \
      -destination "${IOS_SIMULATOR_DESTINATION}" \
      -derivedDataPath "${VERIFY_ALL_DERIVED_ROOT}/ios-simulator"
  fi
}

run_full() {
  echo "verify_all tier: full"
  run_standard
  run_platform_checks
}

if [[ "$selfcheck" -eq 1 ]]; then
  tier="selfcheck"
  echo "verify_all tier: selfcheck"
  run_check "selfcheck pass" true
  run_check "selfcheck fail" false
  run_check "selfcheck after failure" true
  write_report
  count="$("${PYTHON_BIN}" -c \
    "import json;print(len(json.load(open('${REPORT_JSON}'))['checks']))" 2>/dev/null)"
  if [[ "$count" == "1" ]]; then
    echo "self-check OK: exactly 1 failure record in ${REPORT_JSON}"
    exit "$fail"
  fi
  echo "self-check FAILED: expected 1 record, got '${count}'" >&2
  exit 1
fi

case "$tier" in
  fast)
    run_fast
    if [[ "$run_macos" -eq 1 || "$run_ios" -eq 1 ]]; then
      run_platform_checks
    fi
    ;;
  standard)
    run_standard
    if [[ "$run_macos" -eq 1 || "$run_ios" -eq 1 ]]; then
      run_platform_checks
    fi
    ;;
  full)
    run_full
    ;;
esac

echo
# A skipped platform leg must SAY so in the summary (#42 gate audit,
# 2026-08-09): bare `verify_all` skips the Swift/iOS legs by design, and a
# green summary with ~4,400 Swift tests never considered reads as a whole
# run. Absence-as-success, one level up — the FicheroTests target was broken
# on integration for five days and no routine run said "not looked".
if [[ "$run_macos" -eq 0 ]]; then
  echo "NOTE: Swift (macOS) test leg NOT RUN — pass --macos or --full to include it"
fi
if [[ "$run_ios" -eq 0 ]]; then
  echo "NOTE: iOS compile leg NOT RUN — pass --ios or --full to include it"
fi
if [[ "$fail" = 0 ]]; then
  echo "verify_all (${tier}): ALL PASS"
else
  echo "================ verify_all (${tier}): FAILED CHECKS ================"
  for failed in "${FAILED_CHECKS[@]}"; do
    echo "  FAIL ${failed}"
  done
  echo "===================================================================="
  echo "verify_all (${tier}): ${#FAILED_CHECKS[@]} FAILED — see consolidated list above (details inline higher up)"
fi

# Always emit the machine-readable report so tooling has a stable artifact path.
write_report
echo "verify_all report: ${REPORT_JSON}"

# Optionally close the autonomous loop: file the failures as GitHub issues and
# flag the manager. Default OFF so normal runs never spam issues.
if [[ "$file_issues" -eq 1 && "$fail" -ne 0 ]]; then
  echo "verify_all: --file-issues set and failures present — filing issues"
  VERIFY_ALL_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    scripts/verify_to_issues.sh --apply || \
    echo "verify_all: verify_to_issues.sh --apply returned non-zero" >&2
fi

exit "$fail"
