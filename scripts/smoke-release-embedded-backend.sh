#!/usr/bin/env bash
set -euo pipefail

# Smoke-test the Release app's embedded Briefcase engine.
#
# This intentionally launches from ~/Applications, not build/xcode/Products:
# Release builds launched from the build directory show the installer prompt
# before the SwiftUI window task starts the backend.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SRC="$ROOT_DIR/fichero/build/xcode/Products/Release/Fichero.app"
APP_DST="$HOME/Applications/Fichero.app"
HEALTH_PATH="/api/health"
PROBE_LAN=false

usage() {
  cat <<'EOF'
Usage:
  scripts/smoke-release-embedded-backend.sh [--lan]

Options:
  --lan    Also probe https://<configured host>:8765 and the first 192.168.* LAN IP.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --lan) PROBE_LAN=true ;;
    --help|-h) usage; exit 0 ;;
    *) echo "error: unknown argument '$arg'" >&2; usage; exit 2 ;;
  esac
done

if [ ! -d "$APP_SRC" ]; then
  echo "error: $APP_SRC not found. Run scripts/build-release.sh first." >&2
  exit 1
fi

kill_fichero() {
  pkill -x Fichero 2>/dev/null || true
  local pids
  pids="$(pgrep -f 'Fichero Server.app/Contents/MacOS/Fichero Server' || true)"
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null || true
    sleep 2
  fi
  pids="$(pgrep -f 'Fichero Server.app/Contents/MacOS/Fichero Server' || true)"
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
  fi
}

probe_once() {
  local label="$1"
  local url="$2"
  curl -k -fsS --max-time 5 "$url$HEALTH_PATH" >/tmp/fichero-smoke-health.json
  echo "PASS $label $url$HEALTH_PATH"
}

probe_with_retry() {
  local label="$1"
  local url="$2"
  local attempts="${3:-30}"
  for _ in $(seq 1 "$attempts"); do
    if probe_once "$label" "$url" 2>/tmp/fichero-smoke.err; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL $label $url$HEALTH_PATH" >&2
  cat /tmp/fichero-smoke.err >&2
  return 1
}

mkdir -p "$HOME/Applications" "$HOME/Library/Logs/Fichero"
kill_fichero
rm -rf "$APP_DST"
ditto "$APP_SRC" "$APP_DST"
: >"$HOME/Library/Logs/Fichero/engine.log"

open -n "$APP_DST"

for _ in {1..120}; do
  if probe_once loopback "https://127.0.0.1:8765" 2>/tmp/fichero-smoke.err; then
    break
  fi
  sleep 1
done

if ! probe_with_retry loopback "https://127.0.0.1:8765" 5; then
  echo "FAIL loopback https://127.0.0.1:8765$HEALTH_PATH" >&2
  cat /tmp/fichero-smoke.err >&2
  echo "--- engine.log ---" >&2
  tail -n 120 "$HOME/Library/Logs/Fichero/engine.log" >&2
  exit 1
fi

if [ "$PROBE_LAN" = true ]; then
  public_base_url="$(defaults read app.fichero.fichero fichero.remote_access.public_base_url 2>/dev/null || true)"
  if [ -n "$public_base_url" ]; then
    probe_with_retry configured-host "${public_base_url%/}" 30
  fi

  lan_ip="$(ifconfig | awk '/inet 192\\.168\\./ {print $2; exit}')"
  if [ -n "$lan_ip" ]; then
    probe_with_retry lan-ip "https://$lan_ip:8765" 30
  fi
fi

echo "Embedded backend smoke passed."
