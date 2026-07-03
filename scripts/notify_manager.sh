#!/usr/bin/env bash
# notify_manager.sh — a worker tells f_manager it finished an issue / needs a look.
#
# A worker calls this after each commit so the manager gates it promptly instead
# of waiting for the next poll:
#
#   bash scripts/notify_manager.sh "done #2860 (abc1234); next #2870"
#   bash scripts/notify_manager.sh --blocked "need design decision on #2888"
#
# It appends one line to the manager inbox (the manager drains + clears it each
# loop tick, and a Monitor on this file wakes the manager on write). Best-effort
# tmux status-line ping too. ponytail: an append-only file + flock; no daemon,
# no socket — the inbox IS the queue.
set -euo pipefail
INBOX="${FICHERO_MANAGER_INBOX:-$HOME/.fichero-manager-inbox}"
kind="done"
[ "${1:-}" = "--blocked" ] && { kind="BLOCKED"; shift; }
[ "${1:-}" = "--done" ] && shift
msg="$*"
[ -n "$msg" ] || { echo "usage: notify_manager.sh [--blocked] <message>" >&2; exit 2; }

# who am i — the tmux session name is the worker id (f_fichero_codex_engine, …)
worker="${FICHERO_WORKER:-$(tmux display-message -p '#S' 2>/dev/null || echo unknown)}"
ts="$(date '+%Y-%m-%d %H:%M:%S')"

# append one line. O_APPEND makes a single short write atomic (< PIPE_BUF ~512b),
# so concurrent workers won't interleave — no lock needed for one-line messages.
# ponytail: flock is a Linux-ism absent on macOS; the atomic short append covers us.
printf '%s\t%-7s\t%-26s\t%s\n' "$ts" "$kind" "$worker" "$msg" >> "$INBOX"

# best-effort visible ping to the manager window (transient, non-blocking)
tmux display-message -t f_manager "[$kind] $worker: $msg" 2>/dev/null || true
echo "notified f_manager ($kind): $msg"
