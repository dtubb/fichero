#!/usr/bin/env bash
set -euo pipefail

# Create a GitHub release and upload the DMG.
# Reads version from the built app's Info.plist.
# Updates appcast.xml with version info (Sparkle signature is a manual step).
#
# Usage: scripts/create-github-release.sh [--draft]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
APP_PATH="$ROOT_DIR/fichero-swiftui/build/xcode/Products/Release/Fichero.app"
APPCAST_PATH="$ROOT_DIR/fichero-swiftui/appcast.xml"

DRAFT_FLAG=""
for arg in "$@"; do
  case $arg in
    --draft) DRAFT_FLAG="--draft" ;;
    --help|-h) echo "Usage: $0 [--draft]"; exit 0 ;;
  esac
done

# ── Preflight checks ────────────────────────────────────────────────────────
if [ ! -f "$DMG_PATH" ]; then
  echo "error: DMG not found at $DMG_PATH" >&2
  echo "Run scripts/build-release-dmg.sh first." >&2
  exit 1
fi

if [ ! -d "$APP_PATH" ]; then
  echo "error: Release app not found at $APP_PATH" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not found — install with: brew install gh" >&2
  exit 1
fi

# ── Read version from built app ─────────────────────────────────────────────
VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist")
BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_PATH/Contents/Info.plist")
TAG="v${VERSION}"

echo "[1/3] Creating GitHub release: $TAG (build $BUILD)"

DMG_SIZE=$(stat -f%z "$DMG_PATH")

RELEASE_BODY="$(cat <<EOF
## Fichero $VERSION

**Build:** $BUILD

### Installation

1. Download \`Fichero.dmg\` below
2. Open the DMG and drag Fichero to Applications
3. Launch Fichero — the backend starts automatically

### What's New

See [release notes](https://tubb.ca/apps/fichero/) for details.
EOF
)"

gh release create "$TAG" \
  "$DMG_PATH" \
  --title "Fichero $VERSION" \
  --notes "$RELEASE_BODY" \
  $DRAFT_FLAG

echo "[2/3] Release created: $TAG"

# ── Update appcast.xml ──────────────────────────────────────────────────────
echo "[3/3] Updating appcast.xml"

RELEASE_URL="https://github.com/dtubb/fichero/releases/download/${TAG}/Fichero.dmg"
PUB_DATE=$(date -R)

cat > "$APPCAST_PATH" <<APPCAST
<?xml version="1.0" encoding="utf-8"?>
<rss
    version="2.0"
    xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
>
    <channel>
        <title>Fichero Updates</title>
        <link>https://github.com/dtubb/fichero/releases</link>
        <description>Appcast feed for Fichero Sparkle updates.</description>
        <language>en</language>
        <item>
            <title>Fichero $VERSION</title>
            <pubDate>$PUB_DATE</pubDate>
            <sparkle:version>$BUILD</sparkle:version>
            <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
            <enclosure
                url="$RELEASE_URL"
                length="$DMG_SIZE"
                type="application/octet-stream"
                sparkle:edSignature="SIGN_WITH_SPARKLE_PRIVATE_KEY"
            />
        </item>
    </channel>
</rss>
APPCAST

echo
echo "Release: https://github.com/dtubb/fichero/releases/tag/$TAG"
echo "Appcast: $APPCAST_PATH (updated)"
echo
echo "Next: sign the appcast entry with your Sparkle private key:"
echo "  sign_update build/releases/Fichero.dmg"
echo "  Then replace SIGN_WITH_SPARKLE_PRIVATE_KEY in appcast.xml"
