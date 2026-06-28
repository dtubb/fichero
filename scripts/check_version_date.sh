#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$ROOT/fichero/fichero/Info.plist"
PROJECT="$ROOT/fichero/fichero.xcodeproj/project.pbxproj"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage:
  scripts/check_version_date.sh
  scripts/check_version_date.sh --help

Checks the resolved Fichero app version. It reads CFBundleShortVersionString
from fichero/fichero/Info.plist when present, then falls back to the app target's
MARKETING_VERSION in fichero.xcodeproj because this project generates plist keys
at build time.
EOF
  exit 0
fi

version=""
source=""

if [[ -f "$PLIST" ]]; then
  version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST" 2>/dev/null || true)"
  if [[ -n "$version" ]]; then
    source="CFBundleShortVersionString in fichero/fichero/Info.plist"
  fi
fi

if [[ -z "$version" && -f "$PROJECT" ]]; then
  version="$(awk '
    /PRODUCT_BUNDLE_IDENTIFIER = app\.fichero\.fichero;/ { in_app = 1 }
    in_app && /MARKETING_VERSION = / {
      value = $3
      gsub(/;/, "", value)
      print value
      exit
    }
  ' "$PROJECT")"
  if [[ -n "$version" ]]; then
    source="MARKETING_VERSION for app.fichero.fichero in fichero.xcodeproj"
  fi
fi

if [[ -z "$version" ]]; then
  echo "Fichero version-date check: FAIL"
  echo "  Could not resolve CFBundleShortVersionString or app MARKETING_VERSION."
  exit 1
fi

today="$(date +%Y%m%d)"

echo "Fichero version-date check:"
echo "  current version: $version"
echo "  source: $source"

if [[ "$version" =~ ^(20[0-9]{2})\.([0-9]{2})\.([0-9]{2})(\.[0-9]+)?(-[A-Za-z0-9]+)?$ ]]; then
  release_date="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}"
  if [[ "$release_date" > "$today" ]]; then
    echo "  verdict: FAIL - dated version is in the future ($release_date > $today)."
    exit 1
  fi
  if [[ $((10#$today - 10#$release_date)) -gt 10000 ]]; then
    echo "  verdict: FAIL - dated version looks stale by more than one calendar year."
    exit 1
  fi
  echo "  verdict: OK - dated release-style version detected."
  exit 0
fi

if [[ "$version" =~ ^[[:space:]]*$ ]]; then
  echo "  verdict: FAIL - version is empty."
  exit 1
fi

echo "  verdict: FAIL - version is present but not date-shaped."
echo "  expected: YYYY.MM.DD, optional .N same-day build, optional -suffix."
exit 1
