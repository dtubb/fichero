#!/usr/bin/env bash
# build-and-validate.sh — full release validation pipeline
# Usage: scripts/build-and-validate.sh [--skip-notarize]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Tier -> (scheme, config) from FICHERO_RELEASE_TIER (default release).
source "$ROOT_DIR/scripts/tier_build_map.sh"
cd "$ROOT_DIR"

SKIP_NOTARIZE=false
for arg in "$@"; do
  case $arg in
    --skip-notarize) SKIP_NOTARIZE=true ;;
    --help|-h) echo "Usage: $0 [--skip-notarize]"; exit 0 ;;
  esac
done

PASS=0
FAIL=0

ok()   { echo "  ✓ $*"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }

echo
echo "=== Fichero — build & validate ==="
echo

# ── 1. SwiftLint ─────────────────────────────────────────────────────────────
echo "[1/8] SwiftLint"
SWIFTLINT_BIN="${SWIFTLINT_PATH:-$(command -v swiftlint || true)}"
if [ -z "$SWIFTLINT_BIN" ]; then
  SWIFTLINT_BIN="/opt/homebrew/bin/swiftlint"
fi

if [ -x "$SWIFTLINT_BIN" ]; then
  LINT_OUTPUT=$("$SWIFTLINT_BIN" lint fichero/fichero/ 2>&1 || true)
  if echo "$LINT_OUTPUT" | grep -qE "error:"; then
    fail "SwiftLint errors found"
    echo "$LINT_OUTPUT" | grep -E "error:" | head -10
  else
    ok "SwiftLint clean"
  fi
else
  fail "SwiftLint not installed"
fi

# ── 2. Ruff (Python lint) ────────────────────────────────────────────────────
echo "[2/8] Ruff"
RUFF_BIN="${ROOT_DIR}/.venv/bin/ruff"
if [ ! -x "$RUFF_BIN" ]; then
  RUFF_BIN="$(command -v ruff || true)"
fi

if [ -x "$RUFF_BIN" ]; then
  if PYTHONPATH="$ROOT_DIR/fichero-server/src:$ROOT_DIR/fichero-cli/src:$ROOT_DIR/fichero-mcp/src" "$RUFF_BIN" check fichero-server/src/ fichero-cli/src/ fichero-mcp/src/ 2>&1; then
    ok "Ruff clean"
  else
    fail "Ruff violations found"
  fi
else
  fail "Ruff not installed"
fi

# ── 3. pytest (Python tests) ────────────────────────────────────────────────
echo "[3/8] pytest"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -x "$PYTHON_BIN" ]; then
  if PYTHONPATH="$ROOT_DIR/fichero-server/src:$ROOT_DIR/fichero-cli/src:$ROOT_DIR/fichero-mcp/src" "$PYTHON_BIN" -m pytest \
    fichero-server/tests/unit/ \
    --ignore=fichero-server/tests/unit/_archived \
    -q 2>&1; then
    ok "pytest passed"
  else
    fail "pytest failed"
  fi
else
  fail "Python not found"
fi

# ── 4. Briefcase backend build ──────────────────────────────────────────────
echo "[4/8] Briefcase backend build"
cd "$ROOT_DIR/fichero-server"

if ! command -v briefcase >/dev/null 2>&1; then
  fail "Briefcase not installed (pip install briefcase)"
else
  if [ -d "build/server" ]; then
    chmod -R u+w build/server 2>/dev/null || true
    rm -rf build/server
  fi

  if briefcase create macOS --app fichero_server >/dev/null 2>&1; then true; fi
  if briefcase update macOS --app fichero_server 2>&1 && briefcase build macOS --app fichero_server 2>&1; then
    ok "Briefcase backend built"
  else
    fail "Briefcase backend build failed"
  fi
fi

cd "$ROOT_DIR"

# ── 5. Xcode Release build ──────────────────────────────────────────────────
echo "[5/8] Xcode Release build"
XCODE_OUTPUT=$(xcodebuild \
  -project fichero/fichero.xcodeproj \
  -scheme "$MAC_SCHEME" \
  -configuration "$MAC_CONFIG" \
  -derivedDataPath fichero/build/xcode \
  -skipPackagePluginValidation \
  build 2>&1)

if echo "$XCODE_OUTPUT" | grep -q "BUILD SUCCEEDED"; then
  ok "Xcode Release build succeeded"
else
  fail "Xcode Release build failed"
  echo "$XCODE_OUTPUT" | grep "error:" | head -20
fi

# ── 6. Codesign verification ────────────────────────────────────────────────
echo "[6/8] Codesign"
APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/$MAC_CONFIG/Fichero.app"

DEVELOPER_ID=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | awk -F'"' '{print $2}' || true)
if [ -n "$DEVELOPER_ID" ]; then
  codesign --force --sign "$DEVELOPER_ID" --deep --timestamp --options runtime "$APP_PATH" 2>/dev/null
  if codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
    ok "Codesigned with Developer ID"
  else
    fail "Codesign verification failed"
  fi
else
  fail "No Developer ID Application certificate (cannot notarize)"
fi

# ── 7. DMG ──────────────────────────────────────────────────────────────────
echo "[7/8] Build DMG"
STAGE_DIR="$ROOT_DIR/build/releases/dmg-stage"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$ROOT_DIR/build/releases"

if [ -d "$APP_PATH" ]; then
  ditto "$APP_PATH" "$STAGE_DIR/Fichero.app"
  rm -f "$DMG_PATH"
  if hdiutil create -volname "Fichero" -srcfolder "$STAGE_DIR" -ov -format UDZO "$DMG_PATH" >/dev/null 2>&1; then
    DMG_SIZE=$(du -sh "$DMG_PATH" 2>/dev/null | cut -f1)
    ok "DMG created ($DMG_SIZE)"
  else
    fail "DMG creation failed"
  fi
else
  fail "Release app not found at $APP_PATH"
fi

# ── 8. Notarize ─────────────────────────────────────────────────────────────
echo "[8/8] Notarize"
if [ "$SKIP_NOTARIZE" = true ]; then
  echo "  Skipped (--skip-notarize)"
elif [ -z "$DEVELOPER_ID" ]; then
  fail "Cannot notarize without Developer ID Application certificate"
elif ! xcrun notarytool history --keychain-profile "${FICHERO_NOTARIZE_PROFILE:-notarytool}" >/dev/null 2>&1; then
  fail "Notarytool keychain profile not configured (run: xcrun notarytool store-credentials \"notarytool\")"
else
  if xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "${FICHERO_NOTARIZE_PROFILE:-notarytool}" \
    --wait 2>&1; then
    xcrun stapler staple "$DMG_PATH" 2>/dev/null
    ok "Notarized and stapled"
  else
    fail "Notarization failed"
  fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo
echo "=== Results: $PASS passed, $FAIL failed ==="
echo

if [ -f "$DMG_PATH" ]; then
  echo "DMG: $DMG_PATH"
fi

if [ $FAIL -gt 0 ]; then
  exit 1
fi
