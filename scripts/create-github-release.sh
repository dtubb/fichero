#!/usr/bin/env bash
set -euo pipefail

# Create a GitHub release on dtubb/fichero and upload the DMG. Then update
# the appcast in the tubb.ca site repo (served at
# https://tubb.ca/apps/fichero/appcast.xml) so Sparkle can pick up the new
# version. The site's 11ty build passes **/*.xml straight through; deploying
# the site publishes the feed.
#
# Sparkle EdDSA signs the DMG via sign_update from ~/code/sparkle-tools/.
# The Ed25519 private key is read from the macOS Keychain (account "ed25519",
# service "https://sparkle-project.org") — sign_update does this by default
# when no -f/--ed-key-file is passed. The matching public key is baked into
# the app via SPARKLE_PUBLIC_ED_KEY in project.pbxproj -> Info.plist SUPublicEDKey.
#
# Usage: scripts/create-github-release.sh [--draft] [--prerelease] [--dry-run|-n]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Fichero.dmg = beta (default Sparkle channel, the public download);
# Fichero-dev.dmg = dev (<sparkle:channel>dev</sparkle:channel> — only dev
# builds see it, via SparkleChannelDelegate). Both ship per release.
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
DEV_DMG_PATH="$ROOT_DIR/build/releases/Fichero-dev.dmg"
APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/Release/Fichero.app"
STAGED_APP_PATH="$ROOT_DIR/build/releases/dmg-stage/Fichero.app"

RELEASE_REPO="dtubb/fichero"
# The appcast lives in the tubb.ca site repo, NOT in this repo (Daniel's
# 2026-08-25 ruling: tubb.ca/apps/fichero is the permanent product home).
SITE_DIR="${FICHERO_SITE_DIR:-$HOME/code/sites/tubb.ca}"
APPCAST_PATH="$SITE_DIR/apps/fichero/appcast.xml"
APPCAST_URL="https://tubb.ca/apps/fichero/appcast.xml"

# Sparkle CLI tools (downloaded tarball at ~/code/sparkle-tools/, not brew cask)
SPARKLE_BIN="${SPARKLE_BIN:-$HOME/code/sparkle-tools/bin}"
# Private key lives in the Keychain (account "ed25519"); sign_update reads it
# automatically when no -f/--ed-key-file is passed. No on-disk key file.

DRAFT_FLAG=""
PRERELEASE_FLAG=""
DRY_RUN=false
for arg in "$@"; do
  case $arg in
    --draft) DRAFT_FLAG="--draft" ;;
    --prerelease) PRERELEASE_FLAG="--prerelease" ;;
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h) echo "Usage: $0 [--draft] [--prerelease] [--dry-run|-n]"; exit 0 ;;
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
  echo "[DRY RUN] Appcast: $APPCAST_PATH"
fi

# ── Preflight ───────────────────────────────────────────────────────────────
if [ "$DRY_RUN" = false ]; then
  if [ ! -f "$DMG_PATH" ]; then
    echo "error: DMG not found at $DMG_PATH" >&2
    echo "Run scripts/notarize.sh first (which depends on build-release-dmg.sh)." >&2
    exit 1
  fi

  if [ -f "$DEV_DMG_PATH" ]; then
    HAVE_DEV_DMG=true
  else
    HAVE_DEV_DMG=false
    echo "warning: no dev DMG at $DEV_DMG_PATH — releasing the beta DMG only." >&2
    echo "         (the dual-DMG default of release-all.sh builds both)" >&2
  fi

  if [ ! -d "$APP_PATH" ] && [ ! -d "$STAGED_APP_PATH" ]; then
    echo "error: Release app not found at $APP_PATH or $STAGED_APP_PATH" >&2
    exit 1
  fi

  CHECK_APP_PATH="$APP_PATH"
  [ -d "$STAGED_APP_PATH" ] && CHECK_APP_PATH="$STAGED_APP_PATH"
  FEED_URL=$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$CHECK_APP_PATH/Contents/Info.plist")
  if [ "$FEED_URL" != "$APPCAST_URL" ]; then
    echo "error: built app SUFeedURL does not match release appcast" >&2
    echo "  built:    $FEED_URL" >&2
    echo "  expected: $APPCAST_URL" >&2
    echo "Rebuild the release app/DMG after updating SPARKLE_FEED_URL." >&2
    exit 1
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found — install with: brew install gh" >&2
    exit 1
  fi

  if [ ! -x "$SPARKLE_BIN/sign_update" ]; then
    echo "error: sign_update not found at $SPARKLE_BIN/sign_update" >&2
    echo "Sparkle 2.9.1 tarball should be extracted to ~/code/sparkle-tools/" >&2
    exit 1
  fi

  # Keychain key presence (metadata read only — no secret extraction, no GUI prompt).
  if ! security find-generic-password -a "ed25519" -s "https://sparkle-project.org" >/dev/null 2>&1; then
    echo "error: Sparkle Ed25519 private key not found in Keychain" >&2
    echo "  (expected generic-password: account='ed25519', service='https://sparkle-project.org')" >&2
    echo "  Generate with: $SPARKLE_BIN/generate_keys" >&2
    exit 1
  fi

  # The appcast is written into the site repo — its absence means the feed
  # update would silently go nowhere. Fail before the release, not after.
  if [ ! -d "$SITE_DIR/apps/fichero" ]; then
    echo "error: site repo not found at $SITE_DIR/apps/fichero" >&2
    echo "  (set FICHERO_SITE_DIR if the tubb.ca checkout lives elsewhere)" >&2
    exit 1
  fi
else
  echo "[DRY RUN] would check: DMG, app, gh CLI, sign_update, Sparkle keychain key"
fi

# ── Read version + sizes from built app (or use placeholders in dry-run) ────
if [ "$DRY_RUN" = false ]; then
  VERSION_APP_PATH="$APP_PATH"
  [ -d "$STAGED_APP_PATH" ] && VERSION_APP_PATH="$STAGED_APP_PATH"
  VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$VERSION_APP_PATH/Contents/Info.plist")
  BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$VERSION_APP_PATH/Contents/Info.plist")
  DMG_SIZE=$(stat -f%z "$DMG_PATH")
  DMG_SIZE_HUMAN=$(du -h "$DMG_PATH" | cut -f1)
  if [ "$HAVE_DEV_DMG" = true ]; then
    DEV_DMG_SIZE=$(stat -f%z "$DEV_DMG_PATH")
    DEV_DMG_SIZE_HUMAN=$(du -h "$DEV_DMG_PATH" | cut -f1)
  fi
else
  # Rehearse with the version actually stamped in the project, not a placeholder,
  # so the release-notes lookup below is genuinely exercised by --dry-run.
  # #3234: the version lives ONLY in Version.xcconfig (pbxproj has no literals).
  VERSION=$(sed -nE 's/^MARKETING_VERSION = (.+)$/\1/p' \
    "$ROOT_DIR/fichero/Configs/Version.xcconfig" | head -1)
  BUILD="0"
  DMG_SIZE="0"
  DMG_SIZE_HUMAN="0B"
  # Rehearse the dual-DMG path when the dev artifact is on disk.
  if [ -f "$DEV_DMG_PATH" ]; then HAVE_DEV_DMG=true; else HAVE_DEV_DMG=false; fi
  DEV_DMG_SIZE="0"
  DEV_DMG_SIZE_HUMAN="0B"
fi
TAG="v${VERSION}"

# ── Release notes for this version (Sparkle "What's New") ───────────────────
# One source of truth: the `## <VERSION>` section of RELEASE_NOTES.md, rendered
# to HTML and inlined into the appcast <description>. Inline rather than
# sparkle:releaseNotesLink so the update dialog needs no second fetch and no
# hosted URL to keep alive.
#
# A notarized build with no release-notes entry is a bug, not a convenience:
# it ships users an empty "What's New". Fail rather than paper over it.
# `markdown` ships as a transitive dep of mkdocs-material (requirements-docs.txt).
# It lives in the repo-root .venv, which a git worktree does not have — so probe
# for an interpreter that can actually import it rather than guessing a path.
PYBIN=""
for _py in "${FICHERO_PYTHON:-}" "$ROOT_DIR/.venv/bin/python" \
           "$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/\.git$||')/.venv/bin/python" \
           python3; do
  [ -n "$_py" ] || continue
  command -v "$_py" >/dev/null 2>&1 || [ -x "$_py" ] || continue
  if "$_py" -c 'import markdown' >/dev/null 2>&1; then PYBIN="$_py"; break; fi
done
if [ -z "$PYBIN" ]; then
  echo "error: no python with the 'markdown' module (needed to render Sparkle release notes)." >&2
  echo "       tried: \$FICHERO_PYTHON, \$ROOT/.venv, main-checkout .venv, python3" >&2
  echo "       fix:   pip install -r requirements-docs.txt   (or set FICHERO_PYTHON)" >&2
  [ "$DRY_RUN" = true ] || exit 1
fi

set +e
NOTES_BUNDLE="$(
  RN_VERSION="$VERSION" "${PYBIN:-python3}" - "$ROOT_DIR/RELEASE_NOTES.md" <<'PY' 2>&1
import os, re, sys
import markdown
version = os.environ["RN_VERSION"]
src = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"^## %s\s*$(.*?)(?=^## |\Z)" % re.escape(version), src, re.M | re.S)
if not m:
    sys.exit("error: RELEASE_NOTES.md has no '## %s' section — write the release "
             "entry before publishing." % version)
body = m.group(1).strip()
if not body:
    sys.exit("error: RELEASE_NOTES.md section '## %s' is empty." % version)
html = markdown.markdown(body, extensions=["extra", "sane_lists"])
print("===MARKDOWN===")
print(body)
print("===HTML===")
print(html.replace("]]>", "]]&gt;"))  # never terminate the CDATA early
PY
)"
NOTES_RC=$?
set -e

if [ "$NOTES_RC" -ne 0 ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] release notes: $NOTES_BUNDLE"
    echo "[DRY RUN] a real run would ABORT here."
    NOTES_MARKDOWN="(dry run — no notes rendered)"
    NOTES_HTML="<p>(dry run — no notes rendered)</p>"
  else
    echo "$NOTES_BUNDLE" >&2
    exit 1
  fi
else
  NOTES_MARKDOWN="$(printf '%s\n' "$NOTES_BUNDLE" | awk '
    /^===MARKDOWN===$/ { capture=1; next }
    /^===HTML===$/ { capture=0 }
    capture
  ')"
  NOTES_HTML="$(printf '%s\n' "$NOTES_BUNDLE" | awk '
    /^===HTML===$/ { capture=1; next }
    capture
  ')"
  echo "Release notes: rendered '## $VERSION' from RELEASE_NOTES.md (${#NOTES_HTML} bytes of HTML)"
fi
export NOTES_HTML

echo "[1/5] Sparkle-sign DMG(s) (Ed25519 key from Keychain)"
sparkle_sign() {
  # No -f: sign_update reads the private key from the Keychain by default.
  "$SPARKLE_BIN/sign_update" "$1" | grep -oE 'sparkle:edSignature="[^"]+"' | sed -E 's/sparkle:edSignature="([^"]+)"/\1/'
}
if [ "$DRY_RUN" = false ]; then
  ED_SIGNATURE=$(sparkle_sign "$DMG_PATH")
  if [ -z "$ED_SIGNATURE" ]; then
    echo "error: sign_update did not produce a signature" >&2
    exit 1
  fi
  echo "  beta signature: ${ED_SIGNATURE:0:20}…"
  DEV_ED_SIGNATURE=""
  if [ "$HAVE_DEV_DMG" = true ]; then
    DEV_ED_SIGNATURE=$(sparkle_sign "$DEV_DMG_PATH")
    if [ -z "$DEV_ED_SIGNATURE" ]; then
      echo "error: sign_update did not produce a signature for the dev DMG" >&2
      exit 1
    fi
    echo "  dev signature:  ${DEV_ED_SIGNATURE:0:20}…"
  fi
else
  echo "[DRY RUN] would run: $SPARKLE_BIN/sign_update on each DMG (key from Keychain)"
  ED_SIGNATURE="dry-run-placeholder-signature"
  DEV_ED_SIGNATURE="dry-run-placeholder-signature"
fi

# ── Create release on GitHub ────────────────────────────────────────────────
echo "[2/5] Create GitHub release on $RELEASE_REPO ($TAG, build $BUILD, $DMG_SIZE_HUMAN)"
RELEASE_TARGET="${RELEASE_TARGET:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"

RELEASE_BODY="## Installation

1. Download \`Fichero.dmg\` below (\`Fichero-dev.dmg\` is the internal build with ALL features on — expect rough edges)
2. Open the DMG and drag Fichero to Applications
3. Launch Fichero

The app keeps itself up to date via Sparkle — you'll be prompted in-app when a new build is available.

## TestFlight

Mac TestFlight and the universal iPhone/iPad TestFlight build are distributed separately.
For access, contact Daniel for the current TestFlight invite.

## Release Notes

$NOTES_MARKDOWN"

if [ "$DRY_RUN" = false ]; then
  # Idempotent + retried (2026-08-20: a 541MB asset upload 400'd repeatedly
  # through gh, killing the whole step after the release row was created).
  # Create WITHOUT the asset if absent, update notes if present, then upload
  # the asset separately with retries — a re-run finishes a half-done step.
  if gh release view "$TAG" --repo "$RELEASE_REPO" >/dev/null 2>&1; then
    echo "  Release $TAG exists — updating notes"
    gh release edit "$TAG" --repo "$RELEASE_REPO" \
      --title "Fichero $VERSION" --notes "$RELEASE_BODY"
  else
    gh release create "$TAG" \
      --repo "$RELEASE_REPO" \
      --title "Fichero $VERSION" \
      --notes "$RELEASE_BODY" \
      --target "$RELEASE_TARGET" \
      $DRAFT_FLAG \
      $PRERELEASE_FLAG
  fi
  upload_asset() {
    # Idempotent + retried per asset (see comment above).
    local path="$1" name
    name="$(basename "$path")"
    if gh release view "$TAG" --repo "$RELEASE_REPO" --json assets \
        --jq '.assets[].name' 2>/dev/null | grep -qx "$name"; then
      echo "  $name asset already present"
      return 0
    fi
    local upload_attempt
    for upload_attempt in 1 2 3 4 5; do
      if gh release upload "$TAG" "$path" --repo "$RELEASE_REPO" --clobber; then
        return 0
      fi
      echo "  $name upload attempt $upload_attempt failed; retrying in $((upload_attempt * 60))s" >&2
      sleep $((upload_attempt * 60))
    done
    echo "error: $name asset upload failed after 5 attempts" >&2
    exit 1
  }
  upload_asset "$DMG_PATH"
  if [ "$HAVE_DEV_DMG" = true ]; then
    upload_asset "$DEV_DMG_PATH"
  fi
else
  echo "[DRY RUN] would run: gh release create $TAG --repo $RELEASE_REPO --target $RELEASE_TARGET --title \"Fichero $VERSION\" $DRAFT_FLAG $PRERELEASE_FLAG"
fi

RELEASE_URL="https://github.com/$RELEASE_REPO/releases/download/${TAG}/Fichero.dmg"
DEV_RELEASE_URL="https://github.com/$RELEASE_REPO/releases/download/${TAG}/Fichero-dev.dmg"
PUB_DATE=$(date -R)

# ── Update appcast.xml (in the tubb.ca site repo) ───────────────────────────
echo "[3/5] Update appcast.xml"

if [ "$DRY_RUN" = false ]; then
  # Ensure the channel skeleton exists, then insert this release's <item>(s)
  # as the first children — one insert path for seed and update alike. The
  # beta item is channel-less (every install sees it); the dev item carries
  # <sparkle:channel>dev</sparkle:channel>, which only dev builds accept
  # (SparkleChannelDelegate).
  if ! grep -q "<channel>" "$APPCAST_PATH" 2>/dev/null; then
    cat > "$APPCAST_PATH" <<APPCAST
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
    <channel>
        <title>Fichero Updates</title>
        <link>https://tubb.ca/apps/fichero/</link>
        <description>Appcast feed for Fichero Sparkle updates.</description>
        <language>en</language>
    </channel>
</rss>
APPCAST
  fi

  python3 - <<PY
import os, re
from pathlib import Path

p = Path("$APPCAST_PATH")
xml = p.read_text()

# NOTES_HTML arrives via the environment, not shell interpolation: it is
# multi-line HTML and would otherwise have to survive a triple-quoted literal.
notes_html = os.environ["NOTES_HTML"]


def item(title_suffix, channel_line, url, length, signature):
    return ("""        <item>
            <title>Fichero $VERSION""" + title_suffix + """</title>
            <pubDate>$PUB_DATE</pubDate>
""" + channel_line + """            <sparkle:version>$BUILD</sparkle:version>
            <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
            <sparkle:minimumSystemVersion>15.0</sparkle:minimumSystemVersion>
            <description><![CDATA[
""" + notes_html + """
]]></description>
            <enclosure
                url=\"""" + url + """\"
                length=\"""" + length + """\"
                type="application/octet-stream"
                sparkle:edSignature=\"""" + signature + """\"
            />
        </item>
""")


new_items = item("", "", "$RELEASE_URL", "$DMG_SIZE", "$ED_SIGNATURE")
if "$HAVE_DEV_DMG" == "true":
    new_items += item(
        " (dev)",
        "            <sparkle:channel>dev</sparkle:channel>\n",
        "$DEV_RELEASE_URL", "$DEV_DMG_SIZE", "$DEV_ED_SIGNATURE",
    )

# Insert immediately after the first occurrence of <language>...</language>,
# or failing that, immediately after <channel>.
m = re.search(r"(<language>[^<]*</language>\s*\n)", xml)
if m:
    xml = xml[:m.end()] + new_items + xml[m.end():]
else:
    xml = re.sub(r"(<channel>\s*\n)", r"\\1" + new_items, xml, count=1)

p.write_text(xml)
PY

  echo "  Updated: $APPCAST_PATH"

  # Commit the feed in the site repo (COMMIT-ONLY — deploying/pushing the site
  # is Daniel's step; the feed is not live until the site deploys).
  if git -C "$SITE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$SITE_DIR" add "apps/fichero/appcast.xml"
    if ! git -C "$SITE_DIR" diff --cached --quiet; then
      git -C "$SITE_DIR" commit -m "appcast: Fichero $VERSION (build $BUILD)"
      echo "  Committed in site repo — DEPLOY tubb.ca to publish the feed."
    fi
  else
    echo "  warning: $SITE_DIR is not a git repo — appcast written but not committed" >&2
  fi
else
  echo "[DRY RUN] would: update $APPCAST_PATH and commit it in $SITE_DIR"
fi

cd "$ROOT_DIR"

echo "[4/5] Tag source repo"
if [ "$DRY_RUN" = false ]; then
  if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "  Remote tag $TAG already exists, skipping"
  elif git rev-parse "$TAG" >/dev/null 2>&1; then
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
echo "Appcast:  $APPCAST_URL"
echo "DMG (beta): $DMG_PATH ($DMG_SIZE_HUMAN)"
if [ "$HAVE_DEV_DMG" = true ]; then
  echo "DMG (dev):  $DEV_DMG_PATH ($DEV_DMG_SIZE_HUMAN)"
fi
