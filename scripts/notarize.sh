#!/usr/bin/env bash
set -euo pipefail

# Notarize a .dmg OR a .app with Apple and staple the ticket.
#
# BOTH must be notarized and stapled, which is #4491. Stapling only the DMG
# leaves the app the user drags to /Applications carrying no ticket of its own.
# Online that is invisible: Gatekeeper asks Apple. Offline — first launch on a
# plane, or a locked-down machine — there is nothing local to verify against and
# the app may refuse to open. Every release cut from this repo has shipped that
# way, and it has never been noticed because the machine cutting it is online.
#
# notarytool cannot submit a bare .app; it takes a zip, dmg or pkg. So an .app
# is zipped with `ditto -c -k --keepParent` for submission, and the TICKET is
# then stapled to the .app itself — stapler works on the bundle, not the zip,
# and the zip is a transport detail that is thrown away.
#
# Requires: Developer ID Application certificate + notarytool keychain profile.
#
# One-time setup:
#   xcrun notarytool store-credentials "notarytool" \
#     --apple-id "your@email.com" \
#     --team-id "YOUR_TEAM_ID" \
#     --password "app-specific-password"
#
# Usage: scripts/notarize.sh [path-to-dmg-or-app] [--dry-run|-n]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false
POSITIONAL_ARGS=()

for arg in "$@"; do
  case $arg in
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h) echo "Usage: $0 [path-to-dmg-or-app] [--dry-run|-n]"; exit 0 ;;
    *) POSITIONAL_ARGS+=("$arg") ;;
  esac
done

TARGET_PATH="${POSITIONAL_ARGS[0]:-$ROOT_DIR/build/releases/Fichero.dmg}"
# An .app is a directory; a .dmg is a file. The submission artifact differs
# (a zip for the app), the staple target does not.
case "$TARGET_PATH" in
  *.app) TARGET_KIND="app" ;;
  *)     TARGET_KIND="dmg" ;;
esac
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
  echo "[DRY RUN] Target: $TARGET_PATH ($TARGET_KIND)"
  echo "[DRY RUN] Keychain profile: $KEYCHAIN_PROFILE"
else
  if [ "$TARGET_KIND" = "app" ]; then
    if [ ! -d "$TARGET_PATH" ]; then
      echo "error: app not found at $TARGET_PATH" >&2
      exit 1
    fi
  elif [ ! -f "$TARGET_PATH" ]; then
    echo "error: DMG not found at $TARGET_PATH" >&2
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
echo "[2/3] Submitting for notarization: $(basename "$TARGET_PATH")"

# notarytool takes a zip/dmg/pkg, never a bare bundle.
SUBMIT_PATH="$TARGET_PATH"
ZIP_TMP=""
if [ "$TARGET_KIND" = "app" ]; then
  ZIP_TMP="$(dirname "$TARGET_PATH")/$(basename "$TARGET_PATH").notarize.zip"
  run_or_dry rm -f "$ZIP_TMP"
  run_or_dry /usr/bin/ditto -c -k --keepParent "$TARGET_PATH" "$ZIP_TMP"
  SUBMIT_PATH="$ZIP_TMP"
fi

# NO `--wait`. It has failed here with a deadline-exceeded that abandons a
# submission Apple went on to accept, turning a slow release into a failed one.
# Submit, capture the id, then poll `notarytool info` — the established pattern
# in this repo. Do not "simplify" this back to --wait.
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] would run: xcrun notarytool submit $SUBMIT_PATH ${NOTARY_AUTH_ARGS[*]} --output-format json"
  echo "[DRY RUN] would poll: xcrun notarytool info <id> until status != In Progress"
else
  SUBMIT_JSON="$(xcrun notarytool submit "$SUBMIT_PATH" "${NOTARY_AUTH_ARGS[@]}" --output-format json)"
  SUBMISSION_ID="$(printf '%s' "$SUBMIT_JSON" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
  if [ -z "$SUBMISSION_ID" ]; then
    echo "error: notarytool submit returned no submission id" >&2
    printf '%s\n' "$SUBMIT_JSON" >&2
    exit 1
  fi
  echo "  Submission id: $SUBMISSION_ID"

  # 90 polls x 20s = 30 minutes. Generous on purpose: an abandoned submission
  # costs a whole release cycle, and the poll is cheap.
  NOTARY_STATUS="In Progress"
  for _ in $(seq 1 90); do
    sleep 20
    INFO_JSON="$(xcrun notarytool info "$SUBMISSION_ID" "${NOTARY_AUTH_ARGS[@]}" --output-format json 2>/dev/null || true)"
    NOTARY_STATUS="$(printf '%s' "$INFO_JSON" | /usr/bin/python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("status","In Progress"))
except Exception: print("In Progress")')"
    echo "  status: $NOTARY_STATUS"
    [ "$NOTARY_STATUS" = "In Progress" ] || break
  done

  if [ "$NOTARY_STATUS" != "Accepted" ]; then
    echo "error: notarization did not succeed (status: $NOTARY_STATUS)" >&2
    echo "  xcrun notarytool log $SUBMISSION_ID ${NOTARY_AUTH_ARGS[*]}" >&2
    exit 1
  fi
fi

# `if`, NOT `[ -n "$ZIP_TMP" ] && …`. Under `set -e` a bare `test && cmd` whose
# test FAILS is a failing statement, so the DMG path — where ZIP_TMP is empty —
# would have exited 1 here, one line before stapling. Written that way first.
if [ -n "$ZIP_TMP" ]; then
  run_or_dry rm -f "$ZIP_TMP"
fi

# ── 3. Staple the ticket ────────────────────────────────────────────────────
# Stapled to the BUNDLE, not to the zip that was submitted.
echo "[3/3] Stapling notarization ticket"
run_or_dry xcrun stapler staple "$TARGET_PATH"
run_or_dry xcrun stapler validate "$TARGET_PATH"

echo
echo "Notarization complete: $TARGET_PATH"
