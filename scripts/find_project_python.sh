#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-.}"
repo_root="$(cd "$repo_root" && pwd -P)"

local_python="$repo_root/.venv/bin/python"
if [[ -x "$local_python" ]]; then
  printf '%s\n' "$local_python"
  exit 0
fi

common_git_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
  echo "error: cannot locate the project venv outside a git checkout" >&2
  exit 2
}
shared_python="$(dirname "$common_git_dir")/.venv/bin/python"
if [[ -x "$shared_python" ]]; then
  printf '%s\n' "$shared_python"
  exit 0
fi

echo "error: project Python not found; create .venv in the main checkout" >&2
exit 2
