#!/usr/bin/env bash
set -euo pipefail

# Deploy tubb.ca with the Netlify CLI so the appcast create-github-release.sh just wrote goes live.
# Netlify ignores git pushes on this account (2026-11-23), so a committed appcast.xml never reached
# https://tubb.ca/apps/fichero/appcast.xml and release_guard verify-appcast timed out (2026-11-27).
# One deploy per release: an Eleventy build of the site repo, then `netlify deploy --prod --dir _site`.
# Usage: scripts/deploy-appcast.sh   (FICHERO_SITE_DIR: the tubb.ca checkout, default ~/code/sites/tubb.ca)

SITE_DIR="${FICHERO_SITE_DIR:-$HOME/code/sites/tubb.ca}"
if [ ! -f "$SITE_DIR/apps/fichero/appcast.xml" ]; then
  echo "error: no appcast at $SITE_DIR/apps/fichero/appcast.xml (create-github-release.sh writes it first)" >&2
  exit 1
fi
cd "$SITE_DIR"
echo "[1/2] Building tubb.ca with Eleventy"
npx @11ty/eleventy
echo "[2/2] Deploying _site with the Netlify CLI"
netlify deploy --prod --dir _site
