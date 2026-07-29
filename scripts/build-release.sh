#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Release configuration with embedded engine.
# Uses briefcase build to produce Fichero Server.app, then Xcode builds the
# host app. The Xcode "Embed Fichero Server" run-script phase copies the
# engine into Contents/Resources/ during the Release build.
#
# Usage: scripts/build-release.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_ROOT="$ROOT_DIR/fichero-server"
SWIFTUI_ROOT="$ROOT_DIR/fichero"
PROJECT="$SWIFTUI_ROOT/fichero.xcodeproj"
# Tier -> (scheme, config) from FICHERO_RELEASE_TIER (default release).
source "$ROOT_DIR/scripts/tier_build_map.sh"
SCHEME="$MAC_SCHEME"
CONFIGURATION="$MAC_CONFIG"
DERIVED_DATA="$SWIFTUI_ROOT/build/xcode"
APP_PATH="$DERIVED_DATA/Products/$CONFIGURATION/Fichero.app"
SPARKLE_FEED_URL="${SPARKLE_FEED_URL:-https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml}"

SKIP_BACKEND=false
DRY_RUN=false
for arg in "$@"; do
  case $arg in
    --skip-backend) SKIP_BACKEND=true ;;
    --dry-run|-n) DRY_RUN=true ;;
    --skip-openapi-sync)
      echo "error: --skip-openapi-sync removed; sync_openapi_schema.sh now" >&2
      echo "       self-skips when the schema is unchanged. Pre-2026-05-02" >&2
      echo "       silent-stale-bindings bugs (31fc4141, page_content decode)" >&2
      echo "       trace back to this flag being passed through to release builds." >&2
      exit 2
      ;;
    --help|-h) echo "Usage: $0 [--skip-backend] [--dry-run|-n]"; exit 0 ;;
  esac
done

# run_or_dry: execute a command or print it in dry-run mode.
run_or_dry() {
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] would run: $*"
  else
    "$@"
  fi
}

[ "$DRY_RUN" = true ] && echo "[DRY RUN] build-release.sh — printing steps only"

ENGINE_APP="$ENGINE_ROOT/build/fichero_server/macos/app/Fichero Server.app"

# ── 0. Sync OpenAPI schema engine → Swift client ────────────────────────────
# Re-export the engine's openapi.json and copy it into the Swift package so
# the SwiftPM OpenAPIGenerator plugin regenerates Swift types from the
# *current* engine routes. The script self-skips (~2s) when the schema
# hasn't changed, so it's safe on every build — there's no flag to skip it.
# Stale Swift bindings caused #742 (31fc4141) and the page_content decode
# bug (2026-05-02); never let either ship again.
echo "[0/4] Syncing OpenAPI schema engine → Swift client"
run_or_dry "$ENGINE_ROOT/scripts/sync_openapi_schema.sh"

# ── 1. Build engine with Briefcase ──────────────────────────────────────────
if [ "$SKIP_BACKEND" = true ]; then
  echo "[1/4] Skipping engine build (--skip-backend)"
  if [ -d "$ENGINE_APP" ]; then
    echo "  Using existing engine at: $ENGINE_APP"
  else
    echo "  warning: no engine at $ENGINE_APP — Xcode embed phase will fail"
  fi
else
  echo "[1/4] Building engine with Briefcase"
  run_or_dry "$ROOT_DIR/scripts/preflight-embedded-engine.sh" --rebuild

  if [ "$DRY_RUN" = false ]; then
    if [ ! -d "$ENGINE_APP" ]; then
      echo "error: Briefcase build failed — $ENGINE_APP not found" >&2
      exit 1
    fi
    ENGINE_SIZE=$(du -sh "$ENGINE_APP" | cut -f1)
    echo "  Engine built: $ENGINE_APP ($ENGINE_SIZE)"
  fi
fi

if [ "$SKIP_BACKEND" = true ] && [ -d "$ENGINE_APP" ]; then
  echo "  Cleaning embedded engine bundle for release distribution"
  run_or_dry "$ROOT_DIR/scripts/clean-embedded-engine.sh" "$ENGINE_APP"
fi

# ── 2. Xcode Release build ──────────────────────────────────────────────────
# Xcode's CopyFiles build phase copies FicheroBackend.app into Resources
echo "[2/4] Xcode Release build"
echo "  Sparkle feed: $SPARKLE_FEED_URL"
cd "$ROOT_DIR"
run_or_dry xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -derivedDataPath "$DERIVED_DATA" \
  -skipPackagePluginValidation \
  SPARKLE_FEED_URL="$SPARKLE_FEED_URL" \
  build

if [ "$DRY_RUN" = false ] && [ ! -d "$APP_PATH" ]; then
  echo "error: built app not found at $APP_PATH" >&2
  exit 1
fi

# ── 3. Verify codesigning ───────────────────────────────────────────────────
echo "[3/4] Verifying codesign"
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] would run: codesign --verify --deep --strict $APP_PATH"
elif codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
  echo "  Codesign verification: PASS"
else
  echo "  warning: codesign verification issue (may need Developer ID for distribution)"
fi

# Check engine is embedded
if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] would check: $APP_PATH/Contents/Resources/Fichero Server.app"
elif [ -d "$APP_PATH/Contents/Resources/Fichero Server.app" ]; then
  EMBED_SIZE=$(du -sh "$APP_PATH/Contents/Resources/Fichero Server.app" | cut -f1)
  echo "  Engine embedded: $EMBED_SIZE"
else
  echo "  warning: Fichero Server.app not in built app Resources"
fi

echo
echo "Fichero.app (Release): $APP_PATH"
