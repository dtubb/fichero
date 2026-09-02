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

echo "[0/3] Generating release snippets + publication guard"
cd "$ROOT_DIR"
python3 scripts/gen_site_releases.py
python3 scripts/check_docs_publication.py

echo "[1/3] Building MkDocs site → $BUILD_DIR"
mkdocs build --strict

echo "[2/3] Syncing built site to $DEST"
mkdir -p "$DEST"
# --exclude appcast.xml: the Sparkle feed is written into apps/fichero/ by
# create-github-release.sh, NOT by this MkDocs build — --delete would nuke it.
# --exclude images/: the /apps/ index's icon lives there, outside the MkDocs
# build — --delete was one run away from a broken icon on the apps page.
rsync -av --delete --exclude appcast.xml --exclude images/ "$BUILD_DIR/" "$DEST/"

echo "[3/3] Committing and pushing tubb.ca"
cd "$TUBB_SITE"
# Scoped add (2026-09-02): `git add -A` swept every unrelated dirty file in
# the site repo into this commit — the whole-tree-add bug, site edition.
git add apps/fichero
git commit -m "Update Fichero app page" || echo "Nothing to commit"
git push

echo "Done — Netlify will deploy automatically"
