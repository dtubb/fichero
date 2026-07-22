#!/usr/bin/env bash
# verify_embedded_launch.sh -- the missing gate leg: actually LAUNCH the embedded
# app and prove it reaches a live library with no failure splash (#3968).
#
# verify_all's macOS UI leg runs under "Fichero (Dev Local)" (external engine), so
# it can NEVER exercise the embedded spawn path -- which is exactly the path that
# shipped the "library then Can't-Authenticate splash" bug. This script closes
# that hole: it briefcase-builds the engine bundle (unless one is reused) and runs
# the FicheroUITests embedded-launch suite under "Fichero (Dev Embedded)", which
# spawns the REAL bundled engine and asserts a live UI.
#
# Cost: the briefcase build is ~10 min, so this is a --full / opt-in leg, not the
# fast gate. Reuse an existing fresh bundle with FICHERO_REUSE_ENGINE_BUNDLE=1.
#
# Usage:
#   scripts/verify_embedded_launch.sh                 # build engine + run all embedded UX tests
#   FICHERO_REUSE_ENGINE_BUNDLE=1 scripts/verify_embedded_launch.sh
#   FICHERO_UITEST=ColdLaunchReachesLibraryUITests scripts/verify_embedded_launch.sh
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
ROOT="$(pwd)"

SCHEME="Fichero (Dev Embedded)"
PROJECT="fichero/fichero.xcodeproj"
DDPATH="fichero/build/dd-verify"
ENGINE_BUNDLE="fichero-engine/build/engine/macos/app/Fichero Engine.app"
# Default: run every embedded-launch UX test. Narrow with FICHERO_UITEST=<Class>.
ONLY_TESTING="FicheroUITests"
if [[ -n "${FICHERO_UITEST:-}" ]]; then
  ONLY_TESTING="FicheroUITests/${FICHERO_UITEST}"
fi

# 1) Engine bundle. The Xcode "Embed Fichero Engine" phase copies this into the
#    .app; without it the build errors out. Reuse only when explicitly asked (and
#    present) -- a stale bundle silently tests the wrong engine.
if [[ "${FICHERO_REUSE_ENGINE_BUNDLE:-0}" == "1" && -d "$ENGINE_BUNDLE" ]]; then
  echo "-- reusing existing engine bundle ($ENGINE_BUNDLE) --"
else
  echo "-- building engine bundle (briefcase, ~10 min) --"
  if ! ./fichero-engine/scripts/build_backend_bundle.sh; then
    echo "FAIL: engine bundle build failed" >&2
    exit 1
  fi
fi

if [[ ! -d "$ENGINE_BUNDLE" ]]; then
  echo "FAIL: engine bundle missing after build: $ENGINE_BUNDLE" >&2
  exit 1
fi

# 2) Build + run the embedded-launch UI tests against the real bundled engine.
echo "-- xcodebuild test: $SCHEME / $ONLY_TESTING --"
RESULT_BUNDLE="$(mktemp -d)/embedded-launch.xcresult"
# TEST_RUNNER_<VAR> sets <VAR> in the UI-test RUNNER process's environment (the
# process where ProcessInfo runs), which the embedded-leg gate keys on. Setting
# it on the scheme's LaunchAction only reaches the app-under-test, not the runner
# — that mismatch silently SKIPPED the test, so pass it here explicitly.
# Use the dedicated fichero-embedded test plan (it SELECTS the embedded-launch
# tests). The Dev Local verify_all leg uses the `fichero` plan, which lists these
# in skippedTests and stays green. `-only-testing` does NOT override a plan's
# skip, so the two-plan split is what actually gates run-vs-skip deterministically.
xcodebuild -project "$PROJECT" \
  -scheme "$SCHEME" \
  -testPlan fichero-embedded \
  -derivedDataPath "$DDPATH" \
  -destination 'platform=macOS' \
  -resultBundlePath "$RESULT_BUNDLE" \
  -skipPackagePluginValidation \
  test
status=$?

if [[ $status -eq 0 ]]; then
  echo "PASS: embedded launch reached a live library with no failure splash"
else
  echo "FAIL: embedded launch test failed (xcodebuild exit $status) -- result: $RESULT_BUNDLE" >&2
fi
exit $status
