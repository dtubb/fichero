#!/usr/bin/env bash
# Tiered verification entrypoint.
#
#   --fast      Swift lint + cheap guardrails + version-date + OpenAPI model sync
#   --standard  fast + backend unit tests
#   --full      standard + macOS build/test + iPhone/iPad simulator builds
#
# Default is --fast so tooling workers can run the cheap gate without kicking off
# the app build/test suite. Managers/integrators own --full.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

tier="fast"
run_macos=0
run_ios=0
show_help() {
  cat <<'EOF'
Usage:
  scripts/verify_all.sh [--fast|--standard|--full] [--macos] [--ios]

Tiers:
  --fast      swiftlint + ruff + scripts/check_*.py + check_version_date.sh + OpenAPI model sync
  --standard  fast + backend pytest unit tests
  --full      standard + macOS build/test + iPhone/iPad simulator builds

Platforms:
  --macos     run the macOS Xcode build/test leg
  --ios       run the iPhone/iPad simulator build legs (plus visionOS when supported)

Default: --fast
EOF
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
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown verify tier: $arg" >&2
      echo "Usage: scripts/verify_all.sh [--fast|--standard|--full] [--macos] [--ios]" >&2
      exit 2
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  tier="fast"
fi

if [[ "$tier" == "full" && "$run_macos" -eq 0 && "$run_ios" -eq 0 ]]; then
  run_macos=1
  run_ios=1
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
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
XCODE_PROJECT="fichero/fichero.xcodeproj"
XCODE_SCHEME="Fichero"
VISION_SUPPORTED=0

if rg -q 'SUPPORTED_PLATFORMS = ".*xros' "${XCODE_PROJECT}/project.pbxproj"; then
  VISION_SUPPORTED=1
fi

simulator_udid() {
  local idiom="$1"
  SIMULATOR_IDIOM="$idiom" "${PYTHON_BIN}" - <<'PY'
import json
import os
import subprocess
import sys

idiom = os.environ["SIMULATOR_IDIOM"]

if idiom == "iphone":
    runtime_tags = ("iOS",)
    name_tags = ("iPhone",)
elif idiom == "ipad":
    runtime_tags = ("iOS",)
    name_tags = ("iPad",)
elif idiom == "vision":
    runtime_tags = ("xrOS", "visionOS")
    name_tags = ("Vision",)
else:
    raise SystemExit(f"unsupported simulator idiom: {idiom}")

output = subprocess.check_output(
    ["xcrun", "simctl", "list", "devices", "available", "--json"],
    text=True,
)
devices_by_runtime = json.loads(output).get("devices", {})

for runtime, devices in devices_by_runtime.items():
    if not any(tag in runtime for tag in runtime_tags):
        continue
    for device in devices:
        if not device.get("isAvailable"):
            continue
        name = device.get("name", "")
        if any(tag in name for tag in name_tags):
            print(device["udid"])
            raise SystemExit(0)

raise SystemExit(1)
PY
}

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
  if "$@"; then
    echo "PASS ${label}"
  else
    echo "FAIL ${label}"
    fail=1
  fi
}

run_fast() {
  echo "verify_all tier: fast"

  run_check "swiftlint" swiftlint lint --quiet --cache-path .swiftlint-cache fichero/fichero/

  run_check "backend ruff" env PYTHONPATH=fichero-engine/src \
    "${RUFF_CMD[@]}" check fichero-engine/src/

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

  run_check "OpenAPI model sync" env PYTHONPATH=fichero-engine/src \
    "${PYTHON_BIN}" fichero-engine/scripts/validate_model_sync.py
}

run_standard() {
  echo "verify_all tier: standard"
  run_fast

  run_check "backend pytest unit tests" env PYTHONPATH=fichero-engine/src \
    "${PYTEST_CMD[@]}" fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
}

run_platform_checks() {
  if [[ "$run_macos" -eq 1 ]]; then
    run_xcode_build "xcodebuild macOS build" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME}" \
      -destination 'platform=macOS'

    run_xcode_test "xcodebuild macOS test (Swift suite + CrossLanguageGate -> Python gate)" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME}" \
      -destination 'platform=macOS' \
      -resultBundlePath "$(mktemp -d)/verify.xcresult"
  fi

  if [[ "$run_ios" -eq 1 ]]; then
    local iphone_udid
    local ipad_udid

    iphone_udid="$(simulator_udid iphone)" || {
      echo "FAIL xcodebuild iPhone Simulator build"
      fail=1
      return
    }

    ipad_udid="$(simulator_udid ipad)" || {
      echo "FAIL xcodebuild iPad Simulator build"
      fail=1
      return
    }

    run_xcode_build "xcodebuild iPhone Simulator build" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME}" \
      -destination "id=${iphone_udid}"

    run_xcode_build "xcodebuild iPad Simulator build" \
      -project "${XCODE_PROJECT}" \
      -scheme "${XCODE_SCHEME}" \
      -destination "id=${ipad_udid}"

    if [[ "${VISION_SUPPORTED}" -eq 1 ]]; then
      local vision_udid
      vision_udid="$(simulator_udid vision || true)"
      if [[ -n "${vision_udid}" ]]; then
        run_xcode_build "xcodebuild visionOS Simulator build" \
          -project "${XCODE_PROJECT}" \
          -scheme "${XCODE_SCHEME}" \
          -destination "id=${vision_udid}"
      else
        skip_check "xcodebuild visionOS Simulator build" "no available visionOS simulator"
      fi
    else
      skip_check "xcodebuild visionOS Simulator build" "project target does not support visionOS yet"
    fi
  fi
}

run_full() {
  echo "verify_all tier: full"
  run_standard
  run_platform_checks
}

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
if [[ "$fail" = 0 ]]; then
  echo "verify_all (${tier}): ALL PASS"
else
  echo "verify_all (${tier}): FAILURES ABOVE"
fi
exit "$fail"
