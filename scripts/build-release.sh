#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Release configuration with embedded engine.
# Uses briefcase build to produce Fichero Engine.app, then Xcode builds the
# host app. The Xcode "Embed Fichero Engine" run-script phase copies the
# engine into Contents/Resources/ during the Release build.
#
# Usage: scripts/build-release.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_ROOT="$ROOT_DIR/fichero-engine"
SWIFTUI_ROOT="$ROOT_DIR/fichero"
PROJECT="$SWIFTUI_ROOT/fichero.xcodeproj"
SCHEME="Fichero"
CONFIGURATION="Release"
DERIVED_DATA="$SWIFTUI_ROOT/build/xcode"
APP_PATH="$DERIVED_DATA/Products/$CONFIGURATION/Fichero.app"

SKIP_BACKEND=false
for arg in "$@"; do
  case $arg in
    --skip-backend) SKIP_BACKEND=true ;;
    --skip-openapi-sync)
      echo "error: --skip-openapi-sync removed; sync_openapi_schema.sh now" >&2
      echo "       self-skips when the schema is unchanged. Pre-2026-05-02" >&2
      echo "       silent-stale-bindings bugs (31fc4141, page_content decode)" >&2
      echo "       trace back to this flag being passed through to release builds." >&2
      exit 2
      ;;
    --help|-h) echo "Usage: $0 [--skip-backend]"; exit 0 ;;
  esac
done

ENGINE_APP="$ENGINE_ROOT/build/engine/macos/app/Fichero Engine.app"

# ── 0. Sync OpenAPI schema engine → Swift client ────────────────────────────
# Re-export the engine's openapi.json and copy it into the Swift package so
# the SwiftPM OpenAPIGenerator plugin regenerates Swift types from the
# *current* engine routes. The script self-skips (~2s) when the schema
# hasn't changed, so it's safe on every build — there's no flag to skip it.
# Stale Swift bindings caused #742 (31fc4141) and the page_content decode
# bug (2026-05-02); never let either ship again.
echo "[0/4] Syncing OpenAPI schema engine → Swift client"
"$ENGINE_ROOT/scripts/sync_openapi_schema.sh"

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
  cd "$ENGINE_ROOT"

  # Look for briefcase in dedicated venv, then PATH
  if [ -x "$ENGINE_ROOT/.briefcase-venv/bin/briefcase" ]; then
    export PATH="$ENGINE_ROOT/.briefcase-venv/bin:$PATH"
  elif ! command -v briefcase >/dev/null 2>&1; then
    echo "error: briefcase not found. Set up with:" >&2
    echo "  python3.13 -m venv fichero-engine/.briefcase-venv" >&2
    echo "  fichero-engine/.briefcase-venv/bin/pip install briefcase" >&2
    exit 1
  fi

  # briefcase build produces an adhoc-signed .app — we re-sign with
  # Developer ID later in scripts/notarize.sh. Using `build` (not `package`)
  # avoids briefcase's installer-cert path which can't be satisfied with
  # only Apple Development.
  #
  # `briefcase update` first: `briefcase build` alone re-signs the bundle but
  # does NOT re-copy source files, so .py edits ship stale otherwise.
  briefcase update macOS --app engine
  briefcase build macOS --app engine

  if [ ! -d "$ENGINE_APP" ]; then
    echo "error: Briefcase build failed — $ENGINE_APP not found" >&2
    exit 1
  fi
  ENGINE_SIZE=$(du -sh "$ENGINE_APP" | cut -f1)
  echo "  Engine built: $ENGINE_APP ($ENGINE_SIZE)"
fi

# ── 2. Xcode Release build ──────────────────────────────────────────────────
# Xcode's CopyFiles build phase copies FicheroBackend.app into Resources
echo "[2/4] Xcode Release build"
cd "$ROOT_DIR"
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -derivedDataPath "$DERIVED_DATA" \
  -skipPackagePluginValidation \
  build

if [ ! -d "$APP_PATH" ]; then
  echo "error: built app not found at $APP_PATH" >&2
  exit 1
fi

# ── 3. Verify codesigning ───────────────────────────────────────────────────
echo "[3/4] Verifying codesign"
if codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
  echo "  Codesign verification: PASS"
else
  echo "  warning: codesign verification issue (may need Developer ID for distribution)"
fi

# Check engine is embedded
if [ -d "$APP_PATH/Contents/Resources/Fichero Engine.app" ]; then
  EMBED_SIZE=$(du -sh "$APP_PATH/Contents/Resources/Fichero Engine.app" | cut -f1)
  echo "  Engine embedded: $EMBED_SIZE"
else
  echo "  warning: Fichero Engine.app not in built app Resources"
fi

echo
echo "Fichero.app (Release): $APP_PATH"
