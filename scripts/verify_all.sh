#!/usr/bin/env bash
# Tiered verification entrypoint.
#
#   --fast      Swift lint + cheap guardrails + version-date + OpenAPI model sync
#   --standard  fast + backend unit tests
#   --full      standard + xcodebuild test (the historical heavy gate)
#
# Default is --fast so tooling workers can run the cheap gate without kicking off
# the app build/test suite. Managers/integrators own --full.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

tier="fast"
case "${1:-}" in
  ""|--fast)
    tier="fast"
    ;;
  --standard)
    tier="standard"
    ;;
  --full)
    tier="full"
    ;;
  -h|--help)
    cat <<'EOF'
Usage:
  scripts/verify_all.sh [--fast|--standard|--full]

Tiers:
  --fast      swiftlint + scripts/check_*.py + check_version_date.sh + OpenAPI model sync
  --standard  fast + backend pytest unit tests
  --full      standard + xcodebuild test

Default: --fast
EOF
    exit 0
    ;;
  *)
    echo "Unknown verify tier: $1" >&2
    echo "Usage: scripts/verify_all.sh [--fast|--standard|--full]" >&2
    exit 2
    ;;
esac

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

fail=0

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

  echo "-- architecture and tooling guardrails --"
  local guardrail
  for guardrail in scripts/check_*.py; do
    run_check "$(basename "$guardrail")" "${PYTHON_BIN}" "$guardrail"
  done

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

run_full() {
  echo "verify_all tier: full"
  run_standard

  run_check "xcodebuild test (Swift suite + CrossLanguageGate -> Python gate)" \
    xcodebuild test \
      -project fichero/fichero.xcodeproj \
      -scheme Fichero \
      -destination 'platform=macOS' \
      -skipPackagePluginValidation \
      -resultBundlePath "$(mktemp -d)/verify.xcresult"
}

case "$tier" in
  fast)
    run_fast
    ;;
  standard)
    run_standard
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
