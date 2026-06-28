#!/bin/bash
set -e

# Start backend with optional OpenAPI sync/validation.
# Run from repo root: ./fichero-engine/scripts/start_backend.sh [--no-sync|--fast|--reload]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

if [ -n "${FICHERO_PYTHON_BIN:-}" ] && [ -x "${FICHERO_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FICHERO_PYTHON_BIN}"
elif [ -x "$API_ROOT/.venv/bin/python" ]; then
  # Prefer project-local venv over any externally activated environment.
  PYTHON_BIN="$API_ROOT/.venv/bin/python"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
else
  PYTHON_BIN="python3"
fi

SYNC_OPENAPI=true
SKIP_VALIDATION=false
RELOAD=false
UVICORN_SSL_ARGS=()

for arg in "$@"; do
  case $arg in
    --no-sync) SYNC_OPENAPI=false ;;
    --fast) SYNC_OPENAPI=false; SKIP_VALIDATION=true ;;
    --reload) RELOAD=true ;;
    --help|-h)
      echo "Usage: $0 [--no-sync] [--fast] [--reload]"
      echo
      echo "Default starts uvicorn without reload so the real app DuckDB is opened"
      echo "by one process only. Use --reload only with an isolated/test database."
      exit 0
      ;;
  esac
done

DEFAULTS_REMOTE_ENABLED=false
DEFAULTS_PUBLIC_BASE_URL=""
DEFAULTS_BONJOUR_ENABLED=false
if command -v defaults >/dev/null 2>&1; then
  if [ "$(defaults read app.fichero.fichero fichero.remote_access.enabled 2>/dev/null || echo 0)" = "1" ]; then
    DEFAULTS_REMOTE_ENABLED=true
  fi
  DEFAULTS_PUBLIC_BASE_URL="$(defaults read app.fichero.fichero fichero.remote_access.public_base_url 2>/dev/null || true)"
  if [ "$(defaults read app.fichero.fichero fichero.remote_access.bonjour_enabled 2>/dev/null || echo 0)" = "1" ]; then
    DEFAULTS_BONJOUR_ENABLED=true
  fi
fi

if [ -z "${FICHERO_TLS_CERTFILE:-}" ] && [ -z "${FICHERO_TLS_KEYFILE:-}" ]; then
  # Restore persisted Share/remote-access URL when no env override is set.
  if [ -z "${FICHERO_PUBLIC_BASE_URL:-}" ] && [ "$DEFAULTS_REMOTE_ENABLED" = true ] && [ -n "$DEFAULTS_PUBLIC_BASE_URL" ]; then
    FICHERO_PUBLIC_BASE_URL="$DEFAULTS_PUBLIC_BASE_URL"
  fi

  # PHASE 1 (#2603): default to loopback binding. The legacy raw-LAN bind via
  # macOS defaults (macbook-pro-m1.local) is no longer the default; remote
  # access remains available when FICHERO_PUBLIC_BASE_URL is passed explicitly
  # (Phase 2 will wire Tailscale serve here instead of raw LAN).
  if [ -n "${FICHERO_PUBLIC_BASE_URL:-}" ]; then
    PREPARE_URL="$FICHERO_PUBLIC_BASE_URL"
    PREPARE_ALLOW_LOOPBACK=false
  else
    PREPARE_URL="https://127.0.0.1:8765"
    PREPARE_ALLOW_LOOPBACK=true
  fi
  TLS_MANIFEST="$(
    PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" - "$PREPARE_URL" "$PREPARE_ALLOW_LOOPBACK" <<'PY'
import sys
from fichero.remote_access_tls import material_manifest_json, prepare_remote_access_tls

public_base_url = sys.argv[1]
allow_loopback = sys.argv[2] == "true"
material = prepare_remote_access_tls(public_base_url, allow_loopback=allow_loopback)
print(material_manifest_json(material))
PY
  )"
  FICHERO_TLS_CERTFILE="$(
    "$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.stdin.read())["certificate_path"])' <<<"$TLS_MANIFEST"
  )"
  FICHERO_TLS_KEYFILE="$(
    "$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.stdin.read())["key_path"])' <<<"$TLS_MANIFEST"
  )"
  FICHERO_TLS_SPKI_HASH="$(
    "$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.stdin.read())["spki_pin"])' <<<"$TLS_MANIFEST"
  )"
  export FICHERO_TLS_CERTFILE FICHERO_TLS_KEYFILE FICHERO_TLS_SPKI_HASH
  if [ -n "${FICHERO_PUBLIC_BASE_URL:-}" ]; then
    FICHERO_MULTIUSER="${FICHERO_MULTIUSER:-1}"
    FICHERO_ALLOW_NON_LOOPBACK_BIND="${FICHERO_ALLOW_NON_LOOPBACK_BIND:-I_UNDERSTAND_SHARED_SECRET_RISK}"
    FICHERO_BIND_HOST="$(
      "$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.stdin.read())["bind_host"])' <<<"$TLS_MANIFEST"
    )"
    export FICHERO_MULTIUSER FICHERO_ALLOW_NON_LOOPBACK_BIND FICHERO_BIND_HOST FICHERO_PUBLIC_BASE_URL
    if [ "$DEFAULTS_BONJOUR_ENABLED" = true ]; then
      export FICHERO_ENABLE_BONJOUR="${FICHERO_ENABLE_BONJOUR:-1}"
    fi
  fi
  if command -v defaults >/dev/null 2>&1; then
    EXISTING_ENGINE_HOST="$(defaults read app.fichero.fichero fichero.engine.host 2>/dev/null || true)"
    if [[ "$EXISTING_ENGINE_HOST" == http://127.* ]] ||
       [[ "$EXISTING_ENGINE_HOST" == http://localhost:* ]] ||
       [[ "$EXISTING_ENGINE_HOST" == "http://[::1]"* ]] ||
       [[ "$EXISTING_ENGINE_HOST" == "http://[0:0:0:0:0:0:0:1]"* ]]; then
      defaults delete app.fichero.fichero fichero.engine.host 2>/dev/null || true
    fi
    # PHASE 1 (#2603): clear every stored SPKI pin key before writing fresh
    # ones. A regenerated cert must not leave stale advertised vs client
    # pins behind for any previously used bind URL.
    "$PYTHON_BIN" - <<'PY'
import plistlib
import subprocess
import sys

try:
    xml = subprocess.check_output(
        ["defaults", "export", "app.fichero.fichero", "-"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    plist = plistlib.loads(xml.encode("utf-8"))
except Exception:
    plist = {}

prefixes = (
    "fichero.remote_access.advertised_spki_pin|",
    "fichero.remote_access.client_spki_pin|",
)
for key in list(plist.keys()):
    if any(key.startswith(prefix) for prefix in prefixes):
        subprocess.run(
            ["defaults", "delete", "app.fichero.fichero", key],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
PY
    defaults write app.fichero.fichero "fichero.remote_access.client_spki_pin|https://127.0.0.1:8765" \
      -string "$FICHERO_TLS_SPKI_HASH"
    defaults write app.fichero.fichero "fichero.remote_access.advertised_spki_pin|https://127.0.0.1:8765" \
      -string "$FICHERO_TLS_SPKI_HASH"
    if [ "$PREPARE_URL" != "https://127.0.0.1:8765" ]; then
      defaults write app.fichero.fichero "fichero.remote_access.client_spki_pin|$PREPARE_URL" \
        -string "$FICHERO_TLS_SPKI_HASH"
      defaults write app.fichero.fichero "fichero.remote_access.advertised_spki_pin|$PREPARE_URL" \
        -string "$FICHERO_TLS_SPKI_HASH"
    fi
  fi
fi

if [ -n "${FICHERO_TLS_CERTFILE:-}" ] || [ -n "${FICHERO_TLS_KEYFILE:-}" ]; then
  if [ -z "${FICHERO_TLS_CERTFILE:-}" ] || [ -z "${FICHERO_TLS_KEYFILE:-}" ]; then
    echo "FICHERO_TLS_CERTFILE and FICHERO_TLS_KEYFILE must both be set."
    exit 1
  fi
  UVICORN_SSL_ARGS+=(--ssl-certfile "$FICHERO_TLS_CERTFILE" --ssl-keyfile "$FICHERO_TLS_KEYFILE")
fi

UVICORN_BIND_HOST="$(
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" - <<'PY'
from fichero.bind_host import resolve_bind_host

print(resolve_bind_host())
PY
)"

if [ "$SYNC_OPENAPI" = true ]; then
  "$API_ROOT/scripts/sync_openapi_schema.sh"
fi

if [ "$SKIP_VALIDATION" = false ]; then
  "$PYTHON_BIN" "$API_ROOT/scripts/validate_model_sync.py"
fi

export FICHERO_FEATURE_TIER="${FICHERO_FEATURE_TIER:-dev}"
export FICHERO_VALIDATE_MODELS=1
if [ "$RELOAD" = true ]; then
  # Scope --reload to the engine source ONLY. A bare --reload watches the CWD
  # (repo root), which includes agent worktrees under .claude/worktrees/ — every
  # worker edit then triggers a reload storm + RAM blowup. --reload-dir fixes
  # that. Do not use reload against the real app DuckDB; the reloader parent and
  # child can contend for the same single-process DuckDB lock during app import.
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" -m uvicorn fichero.api.main:app --port 8765 \
    --reload --reload-dir "$API_ROOT/src" --host "$UVICORN_BIND_HOST" "${UVICORN_SSL_ARGS[@]}"
else
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" -m uvicorn fichero.api.main:app --port 8765 \
    --host "$UVICORN_BIND_HOST" "${UVICORN_SSL_ARGS[@]}"
fi
