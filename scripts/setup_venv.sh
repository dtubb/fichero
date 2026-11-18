#!/usr/bin/env bash
# One Python environment recipe for every Mac (owner 2026-11-18): the same Python and the same packages
# on the Pro, the iMac and both Airs. fichero-server/.venv is built from uv.lock (--frozen: never re-solved)
# at the Python fichero-server/.python-version pins, with every extra (kg, image, dev); the repo-root
# .venv links to it. Re-run after a lock or Python pin change. Prints the result to compare machines.
# UV_PROJECT_ENVIRONMENT=<dir> builds that venv instead (another checkout's, from this lock) and links nothing.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/fichero-server"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
PY="$(tr -d '[:space:]' < .python-version)"
"$UV" python install "$PY"
ENV_DIR="${UV_PROJECT_ENVIRONMENT:-$ROOT/fichero-server/.venv}"
"$UV" sync --frozen --all-extras --python "$PY"
[ -n "${UV_PROJECT_ENVIRONMENT:-}" ] || ln -sfn fichero-server/.venv "$ROOT/.venv"
printf '%s python %s, %s packages, lock %s\n' "$(hostname -s)" "$("$ENV_DIR/bin/python" -c 'import platform; print(platform.python_version())')" \
  "$("$UV" pip list --python "$ENV_DIR/bin/python" 2>/dev/null | tail -n +3 | wc -l | tr -d ' ')" "$(shasum -a 256 uv.lock | cut -c1-12)"
