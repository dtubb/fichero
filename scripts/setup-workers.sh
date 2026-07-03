#!/usr/bin/env bash
# setup-workers.sh — (re)create the manager's tmux worker fleet.
# Idempotent: existing worktrees/sessions are left running unless --restart.
#
#   bash scripts/setup-workers.sh          # create anything missing, leave running ones alone
#   bash scripts/setup-workers.sh --restart # kill + relaunch every worker session
#   bash scripts/setup-workers.sh --list    # show status, change nothing
#
# ponytail: a flat table + a loop. No orchestration framework — if the fleet
# shape changes, edit the WORKERS array. f_backend/f_manager/f_director are the
# live engine + human + this manager; this script never touches them.
set -euo pipefail

REPO="${FICHERO_REPO:-$HOME/code/fichero}"
WT_ROOT="${FICHERO_WORKTREES:-$HOME/code/fichero-worktrees}"

# session | worktree-name | lane-branch | runtime(codex|claude)
WORKERS=(
  "f_fichero_codex_engine|ms-engine|lane/engine|codex"
  "f_fichero_codex_docs|ms-docs|lane/docs|codex"
  "f_fichero_claude_swiftui|ms-swiftui|lane/swiftui|claude"
  "f_fichero_opus_board|ms-board|lane/board|claude"
  "f_fichero_opus_connection|ms-connection|lane/connection|claude"
  "f_fichero_opus_features|ms-features|lane/features|claude"
)

runtime_cmd() {
  case "$1" in
    codex)  echo "codex --dangerously-bypass-approvals-and-sandbox" ;;
    claude) echo "claude --dangerously-skip-permissions" ;;
    *) echo "ERROR: unknown runtime '$1'" >&2; return 1 ;;
  esac
}

ensure_worktree() {
  local wt="$WT_ROOT/$1" branch="$2"
  if [ -d "$wt" ]; then return 0; fi
  # branch may or may not exist yet; -B creates/resets local branch to origin if present
  git -C "$REPO" fetch origin --quiet || true
  if git -C "$REPO" show-ref --verify --quiet "refs/remotes/origin/${branch#origin/}"; then
    git -C "$REPO" worktree add "$wt" -B "$branch" "origin/${branch#origin/}"
  else
    git -C "$REPO" worktree add "$wt" -b "$branch"   # new lane off current HEAD
  fi
}

case "${1:-}" in
  --list)
    for row in "${WORKERS[@]}"; do
      IFS='|' read -r sess wt branch rt <<< "$row"
      live=$(tmux has-session -t "$sess" 2>/dev/null && echo up || echo DOWN)
      printf '%-28s %-6s %-14s %s\n' "$sess" "$live" "$rt" "$WT_ROOT/$wt"
    done
    exit 0 ;;
esac

RESTART=0; [ "${1:-}" = "--restart" ] && RESTART=1

for row in "${WORKERS[@]}"; do
  IFS='|' read -r sess wt branch rt <<< "$row"
  wt_path="$WT_ROOT/$wt"
  cmd=$(runtime_cmd "$rt")

  ensure_worktree "$wt" "$branch"

  if tmux has-session -t "$sess" 2>/dev/null; then
    if [ "$RESTART" -eq 1 ]; then
      tmux kill-session -t "$sess"
    else
      echo "· $sess already up — leaving it"
      continue
    fi
  fi

  tmux new-session -d -s "$sess" -c "$wt_path"
  # give the shell a beat, then launch the agent runtime
  tmux send-keys -t "$sess" "cd '$wt_path' && $cmd" Enter
  echo "✓ $sess ($rt) → $wt_path"
done

echo "---"
echo "Fleet up. Manager drives them via: tmux send-keys -t <session> -l '<task>'; then Enter twice."
echo "Live engine (f_backend), manager (f_manager), human (f_director) are NOT managed here."
