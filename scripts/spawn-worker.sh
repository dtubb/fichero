#!/usr/bin/env bash
#
# spawn-worker.sh — spin up an autonomous milestone worker in a detached tmux session.
#
# Does everything you'd otherwise type by hand:
#   1. creates a git worktree on a milestone branch (off latest origin/main)
#   2. opens a detached tmux session in that worktree
#   3. activates the shared .venv
#   4. launches the agent (claude / codex) with permissions bypassed
#   5. feeds it the /session-start-milestone-worker prompt scoped to the milestone
#
# Then it prints the one command you run to watch it: `tmux attach -t <session>`.
#
# Usage:
#   scripts/spawn-worker.sh <model> "<milestone>" [session-name]
#
#   <model>      claude | opus | sonnet | haiku | codex
#   <milestone>  exact GitHub milestone title, e.g. "Workflows"
#   session-name optional tmux session name (default: f_<model>_<slug>)
#
# Examples:
#   scripts/spawn-worker.sh codex  "Workflows"
#   scripts/spawn-worker.sh haiku  "Settings & Providers"  f_haiku_settings
#   scripts/spawn-worker.sh sonnet "Image Editing"
#
set -euo pipefail

MODEL="${1:?usage: spawn-worker.sh <model> <milestone> [session-name]}"
MILESTONE="${2:?missing milestone title}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- derive a filesystem/branch-safe slug from the milestone -----------------
slug() { echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g'; }
MSLUG="$(slug "$MILESTONE")"
SESSION="${3:-f_${MODEL}_${MSLUG}}"
BRANCH="ms/${MSLUG}"
# Worktrees live ONLY under ~/code/fichero-worktrees/<name> — NEVER a bare
# ~/code/fichero-<name> sibling (constitution rule #11: a glob-rm of bare
# siblings destroyed the fichero-search project on 2026-06-09).
# Derived from this checkout, overridable with FICHERO_WORKTREES (as setup-workers.sh
# already does). Never hardcode a home path — a clone at ~/dev/fichero must work too.
WT_ROOT="${FICHERO_WORKTREES:-$(dirname "$ROOT")/fichero-worktrees}"
WORKTREE="${WT_ROOT}/${MSLUG}"

# --- pick the agent launch command + skill-invocation prefix -----------------
# Claude invokes skills with a leading '/', Codex with a leading '$'.
case "$MODEL" in
  claude|opus) AGENT_CMD='claude --dangerously-skip-permissions --model opus';   SKILL='/' ;;
  sonnet)      AGENT_CMD='claude --dangerously-skip-permissions --model sonnet'; SKILL='/' ;;
  haiku)       AGENT_CMD='claude --dangerously-skip-permissions --model haiku';  SKILL='/' ;;
  codex)       AGENT_CMD='codex --dangerously-bypass-approvals-and-sandbox';     SKILL='$' ;;
  *) echo "unknown model '$MODEL' (use claude|opus|sonnet|haiku|codex)" >&2; exit 1 ;;
esac

echo "▶ spawning $MODEL worker for milestone '$MILESTONE'"
echo "  session : $SESSION"
echo "  branch  : $BRANCH"
echo "  worktree: $WORKTREE"

# --- refuse to clobber an existing session -----------------------------------
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "✗ tmux session '$SESSION' already exists — attach with: tmux attach -t $SESSION" >&2
  exit 1
fi

# --- create the worktree (off latest origin/main) ----------------------------
git -C "$ROOT" fetch origin --quiet
if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "  (branch $BRANCH exists — reusing)"
  [ -d "$WORKTREE" ] || git -C "$ROOT" worktree add "$WORKTREE" "$BRANCH"
else
  git -C "$ROOT" worktree add "$WORKTREE" -b "$BRANCH" origin/main
fi

# --- the milestone-worker prompt the agent receives on launch ----------------
PROMPT="${SKILL}session-start-milestone-worker milestone: \"${MILESTONE}\". You are the ${MODEL} worker. Work through 5-15 open, unclaimed issues in this milestone. CLAIM each issue before coding (gh issue edit N --add-assignee @me --add-label status:in-progress; skip any issue already assigned or labelled status:in-progress). Verify every issue (ruff+pytest for backend, swiftlint/xcodebuild for Swift) before committing to this branch (${BRANCH}). Push every 2-3 issues. When done or far ahead, run ${SKILL}session-end-worker. Begin by listing unclaimed issues in the milestone."

# --- launch tmux session, activate venv, start agent, feed prompt ------------
tmux new-session -d -s "$SESSION" -c "$WORKTREE"
tmux send-keys -t "$SESSION" "source '${ROOT}/.venv/bin/activate'" Enter
tmux send-keys -t "$SESSION" "$AGENT_CMD" Enter
# give the agent a moment to boot before typing the prompt
sleep 12
tmux send-keys -t "$SESSION" "$PROMPT" Enter

echo ""
echo "✓ worker is up. Watch it with:"
echo "    tmux attach -t $SESSION"
echo "  (detach again with Ctrl-b d)"
