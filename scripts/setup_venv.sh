#!/usr/bin/env bash
# One Python environment for every Mac (owner 2026-11-18), with the same packages the app's embedded engine
# ships: the Pro, the iMac and both Airs run what the user runs. fichero-server/.venv is built the way
# scripts/preflight-embedded-engine.sh builds the bundle:
#   1. uv.lock (--frozen, never re-solved) with every extra, at the Python the repo-root .python-version pins;
#   2. the briefcase `requires` of [tool.briefcase.app.fichero_server] and its .macOS block (spaCy's language
#      models, the PyObjC frameworks, ...), with uv.lock's versions as constraints;
#   3. Kraken and MLX by the same install scripts the bundle uses ([tool.fichero.kraken_bundle], [.mlx_bundle]).
# Then it imports what a Kraken, MLX, YOLO and spaCy recipe needs, and fails naming anything missing.
# The repo-root .venv links to it. Re-run after a lock, pyproject or Python pin change; the last line compares Macs.
# UV_PROJECT_ENVIRONMENT=<dir> builds that venv instead (another checkout's, from this tree) and links nothing.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/fichero-server"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
PY="$(tr -d '[:space:]' < "$ROOT/.python-version")"
ENV_DIR="${UV_PROJECT_ENVIRONMENT:-$ROOT/fichero-server/.venv}"
VPY="$ENV_DIR/bin/python"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

"$UV" python install "$PY"
# 1. the lock. The engine runs from src (PYTHONPATH=src), never an install of one checkout.
"$UV" sync --frozen --all-extras --no-install-project --python "$PY"

# 2. the bundle's own requires, pinned by the lock (as preflight's requirement_installer_args does).
"$UV" export --frozen --all-extras --no-hashes --no-emit-project --no-emit-workspace \
  --format requirements-txt -o "$TMP/lock-constraints.txt" >/dev/null
"$VPY" - "$ROOT/fichero-server/pyproject.toml" > "$TMP/bundle-requires.txt" <<'EOF'
import sys, tomllib
app = tomllib.load(open(sys.argv[1], "rb"))["tool"]["briefcase"]["app"]["fichero_server"]
print("\n".join([*app["requires"], *app.get("macOS", {}).get("requires", [])]))
EOF
"$UV" pip install --python "$VPY" -c "$TMP/lock-constraints.txt" -r "$TMP/bundle-requires.txt" pip

# 3. Kraken and MLX, by the bundle's own steps, into this venv's site-packages.
SITE="$("$VPY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
"$VPY" "$ROOT/scripts/install_kraken_into_engine_bundle.py" "$SITE"
"$VPY" "$ROOT/scripts/install_mlx_into_engine_bundle.py" "$SITE"

# What a recipe needs must import, or this fails naming it.
"$VPY" - <<'EOF'
import importlib.util
need = ["kraken", "htrmopo", "mlx", "mlx_vlm", "ultralytics", "spacy", "es_core_news_sm", "en_core_web_sm", "psutil", "cv2", "Vision"]
missing = [m for m in need if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit(f"error: the venv lacks {', '.join(missing)}: it would not run what the app runs")
EOF

[ -n "${UV_PROJECT_ENVIRONMENT:-}" ] || ln -sfn fichero-server/.venv "$ROOT/.venv"
printf '%s python %s, %s packages, lock %s, pyproject %s\n' "$(hostname -s)" \
  "$("$VPY" -c 'import platform; print(platform.python_version())')" \
  "$("$UV" pip list --python "$VPY" 2>/dev/null | tail -n +3 | wc -l | tr -d ' ')" \
  "$(shasum -a 256 uv.lock | cut -c1-12)" "$(shasum -a 256 pyproject.toml | cut -c1-12)"
