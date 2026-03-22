#!/usr/bin/env bash
set -euo pipefail

# Full release pipeline: validate → GitHub release → deploy site.
# Usage: scripts/release.sh [--draft] [--skip-notarize]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VALIDATE_ARGS=()
RELEASE_ARGS=()

for arg in "$@"; do
  case $arg in
    --draft) RELEASE_ARGS+=("--draft") ;;
    --skip-notarize) VALIDATE_ARGS+=("--skip-notarize") ;;
    --help|-h)
      echo "Usage: $0 [--draft] [--skip-notarize]"
      echo "  --draft          Create GitHub release as draft"
      echo "  --skip-notarize  Skip Apple notarization step"
      exit 0
      ;;
  esac
done

echo "=== Fichero Release Pipeline ==="
echo

# ── 1. Build and validate ───────────────────────────────────────────────────
echo "── Step 1: Build & Validate ──"
"$ROOT_DIR/scripts/build-and-validate.sh" "${VALIDATE_ARGS[@]+"${VALIDATE_ARGS[@]}"}"
echo

# ── 2. Create GitHub release ────────────────────────────────────────────────
echo "── Step 2: GitHub Release ──"
"$ROOT_DIR/scripts/create-github-release.sh" "${RELEASE_ARGS[@]+"${RELEASE_ARGS[@]}"}"
echo

# ── 3. Deploy site ──────────────────────────────────────────────────────────
echo "── Step 3: Deploy Site ──"
"$ROOT_DIR/scripts/deploy-site.sh"
echo

echo "=== Release complete ==="
