#!/usr/bin/env bash
set -euo pipefail

# Notarize a DMG with Apple and staple the ticket.
# Requires: Developer ID Application certificate + notarytool keychain profile.
#
# One-time setup:
#   xcrun notarytool store-credentials "notarytool" \
#     --apple-id "your@email.com" \
#     --team-id "YOUR_TEAM_ID" \
#     --password "app-specific-password"
#
# Usage: scripts/notarize.sh [path-to-dmg]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="${1:-$ROOT_DIR/build/releases/Fichero.dmg}"
KEYCHAIN_PROFILE="${FICHERO_NOTARIZE_PROFILE:-notarytool}"

if [ ! -f "$DMG_PATH" ]; then
  echo "error: DMG not found at $DMG_PATH" >&2
  echo "Run scripts/build-release-dmg.sh first." >&2
  exit 1
fi

# ── 1. Check prerequisites ──────────────────────────────────────────────────
echo "[1/3] Checking prerequisites"

if ! security find-identity -v -p codesigning | grep -q "Developer ID Application"; then
  echo "error: no Developer ID Application certificate found" >&2
  echo "Create one at: https://developer.apple.com/account/resources/certificates" >&2
  exit 1
fi

if ! xcrun notarytool history --keychain-profile "$KEYCHAIN_PROFILE" >/dev/null 2>&1; then
  echo "error: notarytool keychain profile '$KEYCHAIN_PROFILE' not found" >&2
  echo "" >&2
  echo "Set up credentials with:" >&2
  echo "  xcrun notarytool store-credentials \"$KEYCHAIN_PROFILE\" \\" >&2
  echo "    --apple-id \"your@email.com\" \\" >&2
  echo "    --team-id \"YOUR_TEAM_ID\" \\" >&2
  echo "    --password \"app-specific-password\"" >&2
  echo "" >&2
  echo "Or set FICHERO_NOTARIZE_PROFILE to use a different profile name." >&2
  exit 1
fi

echo "  Developer ID: found"
echo "  Keychain profile: $KEYCHAIN_PROFILE"

# ── 2. Submit for notarization ───────────────────────────────────────────────
echo "[2/3] Submitting for notarization: $(basename "$DMG_PATH")"

xcrun notarytool submit "$DMG_PATH" \
  --keychain-profile "$KEYCHAIN_PROFILE" \
  --wait

# ── 3. Staple the ticket ────────────────────────────────────────────────────
echo "[3/3] Stapling notarization ticket"
xcrun stapler staple "$DMG_PATH"

echo
echo "Notarization complete: $DMG_PATH"
