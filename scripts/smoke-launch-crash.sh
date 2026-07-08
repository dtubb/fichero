#!/usr/bin/env bash
set -uo pipefail

# Launch-crash smoke: boot the built Fichero.app and assert it SURVIVES the
# first few seconds of the AppKit run loop.
#
# Why this exists: crashes like #3334 (the NSApplicationFunctionRowController /
# _NSFunctionRowPanel "more Layout Window passes than views" runaway) have NO
# compile-time or headless signature — they only fire once a real window server
# + the Touch Bar/function-row controller are live. verify_all.sh's headless
# macOS tier boots no window server, so it can never reach them. The only thing
# that catches this class is actually launching the .app and watching it.
#
# It DOES open a GUI window and steal focus for ~15s, so it is deliberately NOT
# wired into verify_all.sh. Run it explicitly, on a machine/Space where a window
# popping up is fine.
#
# Exit 0 = app was still alive after the settle window and produced no fresh
#          crash report. Exit 1 = it died / crashed (reason surfaced). Exit 2 =
#          setup error (app not built, etc.).
#
# Usage:
#   scripts/smoke-launch-crash.sh            # Debug build (default)
#   scripts/smoke-launch-crash.sh --release  # Release build
#   scripts/smoke-launch-crash.sh --settle 20

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWIFTUI_ROOT="$ROOT_DIR/fichero"
CONFIGURATION="Debug"
SETTLE=15
REPORT_DIR="$HOME/Library/Logs/DiagnosticReports"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --release) CONFIGURATION="Release" ;;
    --debug)   CONFIGURATION="Debug" ;;
    --settle)  shift; SETTLE="${1:-15}" ;;
    --help|-h) usage; exit 0 ;;
    *) echo "error: unknown argument '$1'" >&2; exit 2 ;;
  esac
  shift
done

APP_PATH="$SWIFTUI_ROOT/build/xcode/Products/$CONFIGURATION/Fichero.app"
if [ ! -d "$APP_PATH" ]; then
  echo "error: $APP_PATH not found — build it first (scripts/build-$([ "$CONFIGURATION" = Release ] && echo release || echo debug).sh)." >&2
  exit 2
fi

# Newest existing Fichero crash report BEFORE launch — anything newer than this
# after launch is ours. (Touchless if the dir doesn't exist yet.)
mkdir -p "$REPORT_DIR"
newest_report_before="$(ls -t "$REPORT_DIR"/Fichero-*.ips 2>/dev/null | head -1 || true)"

# Guardrail: this pops a real GUI window and steals focus. It must never fire
# from a syntax/arg check or an unattended worker. Require an explicit opt-in so
# only a human (or CI) who means it can launch.
if [ "${FICHERO_SMOKE_LAUNCH:-0}" != "1" ]; then
  echo "refusing to launch a GUI window without opt-in." >&2
  echo "  This opens Fichero.app and grabs focus. To run it deliberately:" >&2
  echo "    FICHERO_SMOKE_LAUNCH=1 scripts/smoke-launch-crash.sh --$(echo "$CONFIGURATION" | tr '[:upper:]' '[:lower:]')" >&2
  exit 2
fi

echo "Launching ($CONFIGURATION) and watching ${SETTLE}s for a launch crash…" >&2
pkill -x Fichero 2>/dev/null || true
sleep 1
open -n "$APP_PATH"

# Poll every second: fail fast the moment the process dies or a crash report
# lands, instead of always waiting the full settle window.
crashed=""
for _ in $(seq 1 "$SETTLE"); do
  sleep 1
  newest_now="$(ls -t "$REPORT_DIR"/Fichero-*.ips 2>/dev/null | head -1 || true)"
  if [ -n "$newest_now" ] && [ "$newest_now" != "$newest_report_before" ]; then
    crashed="$newest_now"
    break
  fi
  if ! pgrep -x Fichero >/dev/null 2>&1; then
    # Process gone but no report yet — give the reporter a moment to flush.
    sleep 3
    newest_now="$(ls -t "$REPORT_DIR"/Fichero-*.ips 2>/dev/null | head -1 || true)"
    [ -n "$newest_now" ] && [ "$newest_now" != "$newest_report_before" ] && crashed="$newest_now"
    crashed="${crashed:-__process_gone__}"
    break
  fi
done

pkill -x Fichero 2>/dev/null || true

if [ -n "$crashed" ]; then
  echo "FAIL: Fichero.app did not survive launch." >&2
  if [ "$crashed" = "__process_gone__" ]; then
    echo "  Process exited during the settle window but wrote no crash report." >&2
  else
    echo "  Crash report: $crashed" >&2
    # Surface the exception reason — the one line that names the bug.
    grep -m1 -o '"exception":.*\|NSGenericException[^"]*\|more Layout Window passes[^"]*' "$crashed" 2>/dev/null | head -3 >&2 || true
  fi
  exit 1
fi

echo "PASS: Fichero.app survived ${SETTLE}s post-launch (no crash report)."
