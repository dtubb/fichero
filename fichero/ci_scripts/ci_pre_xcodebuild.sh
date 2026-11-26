#!/bin/sh
# Xcode Cloud pre-xcodebuild (ci.xcode-cloud-swift-only, docs/contributor_manual/specs/harness/github-ci.md).
# The unit tests run inside Fichero.app (TEST_HOST). Its Debug entitlements carry keychain-access-groups, a restricted
# entitlement macOS only honours with a provisioning profile that lists the Mac it runs on; an Xcode Cloud test Mac is in
# no profile, so the signed host is refused at launch ("Failed to install or launch the test runner", RunningBoard error 5).
# For the test build only, the host is signed without that one key. Nothing else changes, and only on Xcode Cloud: this
# script runs nowhere else. The archive and plain build actions keep the file as committed.
set -eu

case "${CI_XCODEBUILD_ACTION:-}" in
  build-for-testing|test-without-building)
    root="${CI_PRIMARY_REPOSITORY_PATH:-$(cd "$(dirname "$0")/../.." && pwd)}"
    ent="$root/fichero/fichero/Fichero.entitlements"
    if /usr/libexec/PlistBuddy -c 'Print :keychain-access-groups' "$ent" >/dev/null 2>&1; then
      /usr/libexec/PlistBuddy -c 'Delete :keychain-access-groups' "$ent"
      echo "Xcode Cloud: the test host is signed without keychain-access-groups (no profile lists this Mac)"
    fi
    ;;
esac
