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
# Usage: scripts/notarize.sh [path-to-dmg] [--dry-run|-n]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false
POSITIONAL_ARGS=()

for arg in "$@"; do
  case $arg in
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h) echo "Usage: $0 [path-to-dmg] [--dry-run|-n]"; exit 0 ;;
    *) POSITIONAL_ARGS+=("$arg") ;;
  esac
done

DMG_PATH="${POSITIONAL_ARGS[0]:-$ROOT_DIR/build/releases/Fichero.dmg}"
KEYCHAIN_PROFILE="${FICHERO_NOTARIZE_PROFILE:-notarytool}"
API_KEY_PATH="${FICHERO_NOTARY_KEY_PATH:-$HOME/Documents/Developer/Certificates/2026-07-5 App Store Connect/AuthKey_2MGYUR786H.p8}"
API_KEY_ID="${FICHERO_NOTARY_KEY_ID:-2MGYUR786H}"
API_ISSUER="${FICHERO_NOTARY_ISSUER:-6d2cfad9-6a3d-48a0-bdcc-9c75c308f812}"
NOTARY_AUTH_ARGS=()

# run_or_dry: execute a command or print it in dry-run mode.
run_or_dry() {
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] would run: $*"
  else
    "$@"
  fi
}

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] notarize.sh — printing steps only, no commands executed"
  echo "[DRY RUN] DMG: $DMG_PATH"
  echo "[DRY RUN] Keychain profile: $KEYCHAIN_PROFILE"
else
  if [ ! -f "$DMG_PATH" ]; then
    echo "error: DMG not found at $DMG_PATH" >&2
    echo "Run scripts/build-release-dmg.sh first." >&2
    exit 1
  fi
fi

# ── 1. Check prerequisites ──────────────────────────────────────────────────
echo "[1/3] Checking prerequisites"

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] would check: security find-identity -v -p codesigning | grep 'Developer ID Application'"
  echo "[DRY RUN] would check: xcrun notarytool history --keychain-profile $KEYCHAIN_PROFILE"
  # Set representative auth args so the dry-run command preview below does not
  # trip `set -u` ("NOTARY_AUTH_ARGS[@]: unbound variable") — this array is only
  # populated in the real branch otherwise.
  NOTARY_AUTH_ARGS=(--keychain-profile "$KEYCHAIN_PROFILE")
else
  if ! security find-identity -v -p codesigning | grep -q "Developer ID Application"; then
    echo "error: no Developer ID Application certificate found" >&2
    echo "Create one at: https://developer.apple.com/account/resources/certificates" >&2
    exit 1
  fi

  if xcrun notarytool history --keychain-profile "$KEYCHAIN_PROFILE" >/dev/null 2>&1; then
    NOTARY_AUTH_ARGS=(--keychain-profile "$KEYCHAIN_PROFILE")
    echo "  Keychain profile: $KEYCHAIN_PROFILE"
  elif [ -f "$API_KEY_PATH" ]; then
    NOTARY_AUTH_ARGS=(--key "$API_KEY_PATH" --key-id "$API_KEY_ID" --issuer "$API_ISSUER")
    echo "  Keychain profile unavailable; using App Store Connect API key: $API_KEY_ID"
  else
    echo "error: no notarization credentials available" >&2
    echo "  missing keychain profile: $KEYCHAIN_PROFILE" >&2
    echo "  missing API key file: $API_KEY_PATH" >&2
    exit 1
  fi

  echo "  Developer ID: found"
fi

# ── 2. Submit for notarization ───────────────────────────────────────────────
echo "[2/3] Submitting for notarization: $(basename "$DMG_PATH")"

run_or_dry xcrun notarytool submit "$DMG_PATH" \
  "${NOTARY_AUTH_ARGS[@]}" \
  --wait

# ── 3. Staple the ticket ────────────────────────────────────────────────────
echo "[3/3] Stapling notarization ticket"
run_or_dry xcrun stapler staple "$DMG_PATH"

echo
echo "Notarization complete: $DMG_PATH"
