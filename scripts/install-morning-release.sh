#!/usr/bin/env bash
# Install (or replace) the morning-release LaunchAgent for this user.
#   FICHERO_NOTIFY_IMESSAGE=<handle> scripts/install-morning-release.sh [HH:MM]   (default 06:00)
#   scripts/install-morning-release.sh --uninstall
# The handle goes only into ~/Library/LaunchAgents, never into the repo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=app.fichero.morning-release
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then rm -f "$DEST"; echo "uninstalled $LABEL"; exit 0; fi
AT="${1:-06:00}"
[[ "$AT" =~ ^([01]?[0-9]|2[0-3]):([0-5][0-9])$ ]] || { echo "error: time must be HH:MM" >&2; exit 2; }
HOUR=$((10#${BASH_REMATCH[1]})); MINUTE=$((10#${BASH_REMATCH[2]}))
LOGDIR="$HOME/Library/Logs/Fichero"
mkdir -p "$LOGDIR" "$(dirname "$DEST")"
sed -e "s|__SCRIPT__|$ROOT/scripts/morning-release.sh|" -e "s|__HOUR__|$HOUR|" -e "s|__MINUTE__|$MINUTE|" \
    -e "s|__NOTIFY__|${FICHERO_NOTIFY_IMESSAGE:-}|" -e "s|__LOGDIR__|$LOGDIR|g" \
    "$ROOT/scripts/launchd/$LABEL.plist" > "$DEST"
plutil -lint "$DEST" >/dev/null
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $LABEL: daily at $(printf '%02d:%02d' "$HOUR" "$MINUTE") → $ROOT/scripts/morning-release.sh"
