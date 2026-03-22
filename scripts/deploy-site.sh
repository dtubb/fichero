#!/usr/bin/env bash
set -euo pipefail

# Deploy Fichero site content to tubb.ca repo and push.
# Syncs site/src/apps/fichero/ → tubb.ca/apps/fichero/
# Usage: scripts/deploy-site.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TUBB_SITE="$HOME/code/sites/tubb.ca"
DEST="$TUBB_SITE/apps/fichero"
SITE_SRC="$ROOT_DIR/site/src/apps/fichero"

if [ ! -d "$TUBB_SITE" ]; then
  echo "error: tubb.ca repo not found at $TUBB_SITE" >&2
  exit 1
fi

if [ ! -d "$SITE_SRC" ]; then
  echo "error: site source not found at $SITE_SRC" >&2
  echo "Expected fichero/site/src/apps/fichero/ to exist." >&2
  exit 1
fi

echo "[1/2] Syncing to $DEST"
mkdir -p "$DEST"
rsync -av --delete "$SITE_SRC/" "$DEST/"

echo "[2/2] Committing and pushing tubb.ca"
cd "$TUBB_SITE"
git add -A
git commit -m "Update Fichero app page" || echo "Nothing to commit"
git push

echo "Done — Netlify will deploy automatically"
