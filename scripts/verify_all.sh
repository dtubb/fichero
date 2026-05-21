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
