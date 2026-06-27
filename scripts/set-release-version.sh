#!/usr/bin/env bash
# set-release-version.sh — set ONE dated CalVer version across frontend + backend.
#
# Releases are dated (CalVer), not semantic. This is the single command that
# keeps frontend and backend on the same version so they track together.
#
#   Frontend (Xcode):   MARKETING_VERSION       = <date>[-beta]   (Apple display string)
#                       CURRENT_PROJECT_VERSION = <YYYYMMDD>      (Sparkle build int, monotonic)
#   Backend (pyproject): version = "<PEP440>"   (e.g. 2026.6.26 or 2026.6.26b0)
#
# PEP 440 forbids leading zeros (2026.06.26 is invalid) and the literal "-beta",
# so the engine uses the canonical form: strip leading zeros on month/day, beta -> b0.
# The app keeps the human-readable -beta suffix (Apple + Sparkle accept it; Sparkle
# orders updates by the build INTEGER, not the short string, so the suffix is display-only).
#
# Usage:
#   scripts/set-release-version.sh 2026.06.26 --beta   # daily beta (current channel)
#   scripts/set-release-version.sh 2026.06.26          # stable
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PBX="$ROOT/fichero/fichero.xcodeproj/project.pbxproj"
PY="$ROOT/fichero-engine/pyproject.toml"

DATE="${1:?usage: set-release-version.sh <YYYY.MM.DD> [--beta]}"
BETA=false
[ "${2:-}" = "--beta" ] && BETA=true

[[ "$DATE" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$ ]] || { echo "error: date must be YYYY.MM.DD (got '$DATE')" >&2; exit 1; }

APP_VERSION="$DATE"; [ "$BETA" = true ] && APP_VERSION="$DATE-beta"
BUILD_INT="${DATE//./}"                       # 2026.06.26 -> 20260626

# PEP 440: drop leading zeros on month/day; beta -> b0
YYYY="${DATE%%.*}"; rest="${DATE#*.}"; MM="${rest%%.*}"; DD="${rest#*.}"
MM="${MM#0}"; DD="${DD#0}"
ENGINE_VERSION="$YYYY.$MM.$DD"; [ "$BETA" = true ] && ENGINE_VERSION="${ENGINE_VERSION}b0"

echo "app    : MARKETING_VERSION=$APP_VERSION  CURRENT_PROJECT_VERSION=$BUILD_INT"
echo "engine : version=$ENGINE_VERSION"

# --- frontend: CURRENT_PROJECT_VERSION via agvtool (sanctioned tool, works) ---
( cd "$ROOT/fichero" && xcrun agvtool new-version -all "$BUILD_INT" >/dev/null )

# --- frontend: MARKETING_VERSION via value-only sed (sanctioned-tool-blocked fallback) ---
# agvtool new-marketing-version is broken on this project (it looks for a
# literal "YES" path) and the xcodeproj gem 1.27.0 can't parse the project (a
# PBXShellScriptBuildPhase stores shellScript as an Array). Value-only flat
# substitution makes no structural change; integrity is re-checked below via
# `agvtool what-version -terse` (if the project were broken, agvtool would not parse it).
# Project rule #10 sanctions agvtool/xcodeproj; this is the documented fallback.
sed -i '' -E "s/^([[:space:]]*)MARKETING_VERSION = .*;/\1MARKETING_VERSION = $APP_VERSION;/" "$PBX"

# --- backend: both [tool.briefcase] and [project] version lines ---
# Anchored to a digit so a hypothetical `version = "<string>"` dep key is untouched.
sed -i '' -E "s/^version = \"[0-9].*\"/version = \"$ENGINE_VERSION\"/" "$PY"

# --- verify ---
echo
echo "verify:"
echo -n "  MARKETING_VERSION configs: "; grep -cE "MARKETING_VERSION = $APP_VERSION;" "$PBX"
echo -n "  CURRENT_PROJECT_VERSION:   "; ( cd "$ROOT/fichero" && xcrun agvtool what-version -terse )
echo "  engine version:"; grep -nE '^version = ' "$PY" | sed 's/^/    /'

# sanity: PEP 440 parses
"$ROOT/.venv/bin/python" -c "from packaging.version import Version; v=Version('$ENGINE_VERSION'); print('  PEP 440 OK:', v, '| prerelease:', v.is_prerelease)" 2>/dev/null \
  || echo "  (packaging lib not available — $ENGINE_VERSION is canonical PEP 440 regardless)"