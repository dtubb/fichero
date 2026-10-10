#!/bin/zsh
# Launch the Mac app as on a first launch: no projects, no settings, no models.
#
#   scripts/fresh-launch.sh [path/to/Fichero.app]   set the real app data aside, launch cold
#   scripts/fresh-launch.sh --restore              quit, put the real app data back
#
# Nothing is deleted. The app's sandbox containers are renamed aside (*.fresh-saved) and renamed
# back on --restore; each cold try is kept as *.fresh-try-<time> for a person to remove.
# cfprefsd caches a sandboxed app's preferences in memory, so moving the container alone still
# brings back every open project: the app is quit and cfprefsd restarted first (2026-10-10).
set -euo pipefail

C="$HOME/Library/Containers"
IDS=(app.fichero.fichero app.fichero.fichero.fichero_server)
APP="${1:-$(cd "$(dirname "$0")/.." && pwd)/fichero/build/xcode/Dev Embedded/Fichero.app}"

quit_app() {
  [[ "${FICHERO_FRESH_TEST:-}" == "1" ]] && return 0  # its test runs in a throwaway HOME, app untouched
  pkill -f "Fichero.app/Contents/MacOS/Fichero$" 2>/dev/null || true
  for _ in {1..60}; do
    pgrep -f "Fichero.app/Contents/MacOS/Fichero$|Fichero Server.app/Contents/MacOS" >/dev/null || break
    sleep 2
  done
  if pgrep -f "Fichero.app/Contents/MacOS/Fichero$|Fichero Server.app/Contents/MacOS" >/dev/null; then
    echo "Fichero is still running; quit it and try again." >&2; exit 1
  fi
  killall -u "$USER" cfprefsd 2>/dev/null || true
  sleep 1
}

if [[ "${1:-}" == "--restore" ]]; then
  [[ -d "$C/${IDS[1]}.fresh-saved" ]] || { echo "Nothing to restore: no ${IDS[1]}.fresh-saved." >&2; exit 1; }
  quit_app
  stamp=$(date +%Y%m%d-%H%M%S)
  for id in $IDS; do
    [[ -d "$C/$id" ]] && mv "$C/$id" "$C/$id.fresh-try-$stamp"
    [[ -d "$C/$id.fresh-saved" ]] && mv "$C/$id.fresh-saved" "$C/$id"
  done
  echo "Restored. The cold try is kept as $C/*.fresh-try-$stamp"
  exit 0
fi

[[ -d "$C/${IDS[1]}.fresh-saved" ]] && { echo "Already set aside; run --restore first." >&2; exit 1; }
[[ -d "$APP" ]] || { echo "No app at $APP" >&2; exit 1; }
quit_app
for id in $IDS; do
  [[ -d "$C/$id" ]] && mv "$C/$id" "$C/$id.fresh-saved"
done
echo "Real app data set aside as $C/*.fresh-saved; restore with: $0 --restore"
[[ "${FICHERO_FRESH_NO_LAUNCH:-}" == "1" ]] || open "$APP"
