#!/usr/bin/env bash
set -euo pipefail

# Create a GitHub release on dtubb/fichero-releases (the public release repo
# kept separate from the source repo so the source repo stays slim) and
# upload the DMG. Then update appcast.xml in that same repo so Sparkle on
# users' machines picks up the new version.
#
# Sparkle EdDSA signs the DMG via sign_update from ~/sparkle-tools/.
#
# Usage: scripts/create-github-release.sh [--draft] [--dry-run|-n]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/Release/Fichero.app"

# Public release repo — separate from source repo to keep source repo slim
RELEASE_REPO="dtubb/fichero-releases"
RELEASE_REPO_DIR="${FICHERO_RELEASES_DIR:-$HOME/code/fichero-releases}"

# Sparkle CLI tools (downloaded tarball, not brew cask)
SPARKLE_BIN="${SPARKLE_BIN:-$HOME/sparkle-tools/bin}"
SPARKLE_PRIVATE_KEY="${SPARKLE_PRIVATE_KEY:-$HOME/.sparkle/fichero_ed_private_key}"

DRAFT_FLAG=""
DRY_RUN=false
for arg in "$@"; do
  case $arg in
    --draft) DRAFT_FLAG="--draft" ;;
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h) echo "Usage: $0 [--draft] [--dry-run|-n]"; exit 0 ;;
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

if [ "$DRY_RUN" = true ]; then
  echo "[DRY RUN] create-github-release.sh — printing steps only, no commands executed"
  echo "[DRY RUN] DMG: $DMG_PATH"
  echo "[DRY RUN] Release repo: $RELEASE_REPO"
fi

# ── Preflight ───────────────────────────────────────────────────────────────
if [ "$DRY_RUN" = false ]; then
  if [ ! -f "$DMG_PATH" ]; then
    echo "error: DMG not found at $DMG_PATH" >&2
    echo "Run scripts/notarize.sh first (which depends on build-release-dmg.sh)." >&2
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

  if [ ! -x "$SPARKLE_BIN/sign_update" ]; then
    echo "error: sign_update not found at $SPARKLE_BIN/sign_update" >&2
    echo "Sparkle 2.9.1 tarball should be extracted to ~/sparkle-tools/" >&2
    exit 1
  fi

  if [ ! -f "$SPARKLE_PRIVATE_KEY" ]; then
    echo "error: Sparkle private key not found at $SPARKLE_PRIVATE_KEY" >&2
    echo "Generate with: $SPARKLE_BIN/generate_keys" >&2
    exit 1
  fi
else
  echo "[DRY RUN] would check: DMG, app, gh CLI, sign_update, Sparkle private key"
fi

# ── Read version + sizes from built app (or use placeholders in dry-run) ────
if [ "$DRY_RUN" = false ]; then
  VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist")
  BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_PATH/Contents/Info.plist")
  DMG_SIZE=$(stat -f%z "$DMG_PATH")
  DMG_SIZE_HUMAN=$(du -h "$DMG_PATH" | cut -f1)
else
  VERSION="0.0.0-dry"
  BUILD="0"
  DMG_SIZE="0"
  DMG_SIZE_HUMAN="0B"
fi
TAG="v${VERSION}"

echo "[1/5] Sparkle-sign DMG"
if [ "$DRY_RUN" = false ]; then
  ED_SIGNATURE=$("$SPARKLE_BIN/sign_update" "$DMG_PATH" -f "$SPARKLE_PRIVATE_KEY" | grep -oE 'sparkle:edSignature="[^"]+"' | sed -E 's/sparkle:edSignature="([^"]+)"/\1/')
  if [ -z "$ED_SIGNATURE" ]; then
    echo "error: sign_update did not produce a signature" >&2
    exit 1
  fi
  echo "  Signature: ${ED_SIGNATURE:0:20}…"
else
  echo "[DRY RUN] would run: $SPARKLE_BIN/sign_update $DMG_PATH -f $SPARKLE_PRIVATE_KEY"
  ED_SIGNATURE="dry-run-placeholder-signature"
fi

# ── Create release on fichero-releases ──────────────────────────────────────
echo "[2/5] Create GitHub release on $RELEASE_REPO ($TAG, build $BUILD, $DMG_SIZE_HUMAN)"

RELEASE_BODY="## Fichero ${VERSION}

**Build:** ${BUILD}

### Installation

1. Download \`Fichero.dmg\` below
2. Open the DMG and drag Fichero to Applications
3. Launch Fichero — the engine starts automatically

### Notes

See [release notes](https://tubb.ca/apps/fichero/) for what's new."

if [ "$DRY_RUN" = false ]; then
  gh release create "$TAG" \
    "$DMG_PATH" \
    --repo "$RELEASE_REPO" \
    --title "Fichero $VERSION" \
    --notes "$RELEASE_BODY" \
    $DRAFT_FLAG
else
  echo "[DRY RUN] would run: gh release create $TAG --repo $RELEASE_REPO --title \"Fichero $VERSION\" $DRAFT_FLAG"
fi

RELEASE_URL="https://github.com/$RELEASE_REPO/releases/download/${TAG}/Fichero.dmg"
PUB_DATE=$(date -R)

# ── Update appcast.xml in fichero-releases working copy ─────────────────────
echo "[3/5] Update appcast.xml in $RELEASE_REPO"

if [ "$DRY_RUN" = false ]; then
  if [ ! -d "$RELEASE_REPO_DIR" ]; then
    echo "  Cloning $RELEASE_REPO to $RELEASE_REPO_DIR"
    git clone "https://github.com/$RELEASE_REPO.git" "$RELEASE_REPO_DIR"
  fi

  cd "$RELEASE_REPO_DIR"
  git pull --rebase

  APPCAST_PATH="$RELEASE_REPO_DIR/appcast.xml"

  # Append a new <item> before </channel>. If appcast.xml is the placeholder
  # skeleton (no items yet), seed it from scratch. Otherwise insert in place.
  if ! grep -q "<item>" "$APPCAST_PATH" 2>/dev/null; then
    cat > "$APPCAST_PATH" <<APPCAST
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
    <channel>
        <title>Fichero Updates</title>
        <link>https://github.com/$RELEASE_REPO/releases</link>
        <description>Appcast feed for Fichero Sparkle updates.</description>
        <language>en</language>
        <item>
            <title>Fichero $VERSION</title>
            <pubDate>$PUB_DATE</pubDate>
            <sparkle:version>$BUILD</sparkle:version>
            <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
            <sparkle:minimumSystemVersion>15.0</sparkle:minimumSystemVersion>
            <enclosure
                url="$RELEASE_URL"
                length="$DMG_SIZE"
                type="application/octet-stream"
                sparkle:edSignature="$ED_SIGNATURE"
            />
        </item>
    </channel>
</rss>
APPCAST
  else
    # Insert new <item> as the first child of <channel>
    python3 - <<PY
import re
from pathlib import Path

p = Path("$APPCAST_PATH")
xml = p.read_text()

new_item = """        <item>
            <title>Fichero $VERSION</title>
            <pubDate>$PUB_DATE</pubDate>
            <sparkle:version>$BUILD</sparkle:version>
            <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
            <sparkle:minimumSystemVersion>15.0</sparkle:minimumSystemVersion>
            <enclosure
                url="$RELEASE_URL"
                length="$DMG_SIZE"
                type="application/octet-stream"
                sparkle:edSignature="$ED_SIGNATURE"
            />
        </item>
"""

# Insert immediately after the first occurrence of <language>...</language>,
# or failing that, immediately after <channel>.
m = re.search(r"(<language>[^<]*</language>\s*\n)", xml)
if m:
    xml = xml[:m.end()] + new_item + xml[m.end():]
else:
    xml = re.sub(r"(<channel>\s*\n)", r"\\1" + new_item, xml, count=1)

p.write_text(xml)
PY
  fi

  git add appcast.xml
  git commit -m "release: $TAG"
  git push
else
  echo "[DRY RUN] would: clone/pull $RELEASE_REPO, update appcast.xml, git commit + push"
fi

cd "$ROOT_DIR"

echo "[4/5] Tag source repo"
if [ "$DRY_RUN" = false ]; then
  if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "  Tag $TAG already exists in source repo, skipping"
  else
    git tag -a "$TAG" -m "Fichero $VERSION (build $BUILD)"
    git push origin "$TAG"
  fi
else
  echo "[DRY RUN] would run: git tag -a $TAG + git push origin $TAG"
fi

echo "[5/5] Done"
echo
echo "Release:  https://github.com/$RELEASE_REPO/releases/tag/$TAG"
echo "Appcast:  https://raw.githubusercontent.com/$RELEASE_REPO/main/appcast.xml"
echo "DMG:      $DMG_PATH ($DMG_SIZE_HUMAN)"
