#!/usr/bin/env bash
set -euo pipefail

# Deploy the Fichero MkDocs site to the tubb.ca repo and push.
# Builds the MkDocs site (mkdocs.yml at repo root, docs_dir: docs) into
# _site_build, then syncs the built HTML → tubb.ca/apps/fichero/.
# Usage: scripts/deploy-site.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TUBB_SITE="$HOME/code/sites/tubb.ca"
DEST="$TUBB_SITE/apps/fichero"
BUILD_DIR="$ROOT_DIR/_site_build"

if ! command -v mkdocs >/dev/null 2>&1; then
  echo "error: mkdocs not found. Install with: pip install -r requirements-docs.txt" >&2
  exit 1
fi

if [ ! -d "$TUBB_SITE" ]; then
  echo "error: tubb.ca repo not found at $TUBB_SITE" >&2
  exit 1
fi

echo "[1/3] Building MkDocs site → $BUILD_DIR"
cd "$ROOT_DIR"
mkdocs build --strict

echo "[2/3] Syncing built site to $DEST"
mkdir -p "$DEST"
rsync -av --delete "$BUILD_DIR/" "$DEST/"

echo "[3/3] Committing and pushing tubb.ca"
cd "$TUBB_SITE"
git add -A
git commit -m "Update Fichero app page" || echo "Nothing to commit"
git push

echo "Done — Netlify will deploy automatically"
