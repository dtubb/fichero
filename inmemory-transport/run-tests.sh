#!/usr/bin/env bash
# Headless gate for the in-memory ASGI transport: swift test + pytest.
# No Xcode. Isolates app-state paths so it never touches a running engine's
# locked app.duckdb or clobbers its ~/Library/.../.api-key.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="$REPO_ROOT/inmemory-transport"

# --- Python runtime (edit for your machine / CI; no paths are hardcoded in code) ---
: "${PYTHON_LIBRARY:=/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Python}"
: "${PYTHONHOME:=/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12}"
# Engine source (this worktree, so the auth.py inmemory marker is present) + a
# venv with fastapi/httpx/duckdb installed.
: "${FICHERO_ENGINE_SRC:=$REPO_ROOT/fichero-engine/src}"
: "${FICHERO_VENV_SITE_PACKAGES:=$REPO_ROOT/.venv/lib/python3.12/site-packages}"
if [[ ! -d "$FICHERO_VENV_SITE_PACKAGES" ]]; then
  FICHERO_VENV_SITE_PACKAGES="$HOME/code/fichero/.venv/lib/python3.12/site-packages"
fi
# Isolated app-state dir (relocates app.duckdb away from the locked real one).
FICHERO_BASE_PATH="$(mktemp -d -t inmem-base)"

export PYTHON_LIBRARY PYTHONHOME FICHERO_ENGINE_SRC FICHERO_VENV_SITE_PACKAGES FICHERO_BASE_PATH

echo "== swift test =="
( cd "$PKG_DIR" && swift test )

echo "== pytest =="
PYTEST_PY="$FICHERO_VENV_SITE_PACKAGES/../../../bin/python"
"${PYTEST_PY}" -m pytest "$PKG_DIR/pytest" -q

echo "ALL GREEN"
