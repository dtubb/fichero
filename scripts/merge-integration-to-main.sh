#!/usr/bin/env bash
# merge-integration-to-main.sh — fast-forward the `integration` lane into
# `main` and push, as the pre-step before scripts/release-all.sh.
#
# release-all.sh builds from the MAIN checkout on `main`, but integration work
# lands on the `integration` branch in its own worktree and release-all.sh never
# merges it. Run THIS first so the release actually ships integration's work:
#
#   cd <main checkout>          # e.g. ~/code/fichero
#   scripts/merge-integration-to-main.sh
#   scripts/release-all.sh --github --dev
#
# Refuses anything that isn't a clean fast-forward — no merge commits. A
# diverged `integration` means its worktree needs rebasing onto main first; fix
# that in the integration worktree, not here.
#
# It discards only files that a later step deterministically recreates:
#   * the generated OpenAPI copies — integration's committed spec plus the
#     post-merge sync_openapi_schema.sh run rewrite them;
#   * the dated release stamps — release-all.sh runs set-release-version.sh up
#     front, which rewrites exactly these three paths (and only renames
#     RELEASE_NOTES.md's top `## ` heading, refusing if none matches, so no
#     hand-written note text is at risk).
# Every other dirty path is still a hard error.

REGENERATED_FILES=(
  "docs/contributor/api-reference/openapi.json"
  "fichero-server/tests/contracts/openapi.json"
  "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"
  "RELEASE_NOTES.md"
  "fichero-server/pyproject.toml"
  "fichero/fichero.xcodeproj/project.pbxproj"
)

is_regenerated_file() {
  local path="$1"
  local generated
  for generated in "${REGENERATED_FILES[@]}"; do
    [ "$path" = "$generated" ] && return 0
  done
  return 1
}

restore_regenerated_files() {
  local status path
  local other_changes=()
  while IFS= read -r status; do
    path="${status:3}"
    if ! is_regenerated_file "$path" \
      && { [ "$path" != "scripts/merge-integration-to-main.sh" ] \
        || ! git diff --quiet "$SOURCE_BRANCH" -- "$path"; }; then
      other_changes+=("$status")
    fi
  done < <(git status --short)

  if [ "${#other_changes[@]}" -gt 0 ]; then
    echo "error: working tree has changes outside regenerated files:" >&2
    printf '  %s\n' "${other_changes[@]}" >&2
    exit 1
  fi

  if [ -z "$(git status --short)" ]; then
    return
  fi

  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] would restore regenerated files and installed helper from HEAD"
  else
    echo "── Restore regenerated files (OpenAPI + release stamps) ──"
    git restore --staged --worktree -- "${REGENERATED_FILES[@]}" \
      scripts/merge-integration-to-main.sh
  fi
}

# Usage:
#   scripts/merge-integration-to-main.sh [--dry-run] [--source <branch>]
#
# --dry-run   resolve + verify but do not restore, merge, or push.
# --source    branch to merge in (default: integration).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SOURCE_BRANCH="integration"
DRY_RUN=false
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
    --source) shift; SOURCE_BRANCH="${1:?--source requires a branch name}" ;;
    --help|-h) sed -n '2,65p' "$0"; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" != "main" ]; then
  echo "error: not on 'main' (on '$BRANCH'). Run from the main checkout:" >&2
  echo "  cd $ROOT_DIR && git checkout main" >&2
  exit 1
fi

echo "── Fetch origin ──"
git fetch origin --quiet

restore_regenerated_files

if ! git merge-base --is-ancestor HEAD origin/main; then
  echo "error: local main has commits not on origin/main — push or reconcile it first." >&2
  exit 1
fi

if ! git merge-base --is-ancestor origin/main HEAD; then
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] would: git merge --ff-only origin/main"
  else
    echo "── Fast-forward main to origin/main ──"
    git merge --ff-only origin/main
  fi
fi

if ! git show-ref --verify --quiet "refs/heads/$SOURCE_BRANCH"; then
  echo "error: branch '$SOURCE_BRANCH' not found locally." >&2
  echo "  Its worktree must exist and be on $SOURCE_BRANCH." >&2
  exit 1
fi

echo "── Verify $SOURCE_BRANCH is a clean fast-forward over origin/main ──"
if ! git merge-base --is-ancestor origin/main "$SOURCE_BRANCH"; then
  echo "error: '$SOURCE_BRANCH' has diverged from main — not a fast-forward." >&2
  echo "  Rebase $SOURCE_BRANCH onto main in its worktree first:" >&2
  echo "    git -C <${SOURCE_BRANCH}-worktree> rebase main" >&2
  exit 1
fi

AHEAD="$(git rev-list --count "origin/main..$SOURCE_BRANCH")"
if [ "$AHEAD" -eq 0 ]; then
  echo "main is already at $SOURCE_BRANCH ($(git rev-parse --short origin/main)) — nothing to merge."
else
  echo "  $SOURCE_BRANCH is $AHEAD commit(s) ahead of origin/main:"
  git log --oneline "origin/main..$SOURCE_BRANCH" | sed 's/^/    /'
fi

if [ "$DRY_RUN" = true ]; then
  echo
  echo "[DRY RUN] would: git merge --ff-only $SOURCE_BRANCH && git push origin main"
  exit 0
fi

if [ "$AHEAD" -eq 0 ]; then
  echo "Nothing to push."
else
  echo
  echo "── Fast-forward main to $SOURCE_BRANCH ──"
  git merge --ff-only "$SOURCE_BRANCH"
  echo
  echo "── Sync generated OpenAPI contracts ──"
  ./fichero-server/scripts/sync_openapi_schema.sh
  if ! git diff --quiet; then
    git add docs/contributor/api-reference/openapi.json \
      fichero-cli/src/fichero_cli/openapi_surface_generated.py \
      fichero-server/tests/contracts/endpoints.json \
      fichero-server/tests/contracts/openapi.json \
      fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json
    git commit --author='Claude (GPT-5.6 Terra) <noreply@anthropic.com>' \
      -m 'chore(openapi): sync generated contracts' \
      -m 'Co-Authored-By: Claude <noreply@anthropic.com>'
  fi
  echo
  echo "── Push main to origin ──"
  git push origin main
fi

echo
echo "✓ main is now at $(git rev-parse --short HEAD)."
echo "  Next: scripts/release-all.sh --github --dev"