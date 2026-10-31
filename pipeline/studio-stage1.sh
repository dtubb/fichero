#!/bin/bash
# Studio trial, stage 1: the named items through the runner and Pi (Sonnet 5.5 codes and reviews; CODER=haiku for Haiku 5.5).
# usage: pipeline/studio-stage1.sh [anthropic|openrouter] [issue ...]      default: anthropic, items 6214 6100
# openrouter: both models via OpenRouter, pinned to the Anthropic endpoint (the OpenRouter key in ~/.config/openrouter/).
# anthropic: direct, with the Anthropic key in ~/.config/anthropic/.
# Spends real money (est. US$2-6 for three items, US$1.5-4 for two; the daily cap is 8). Windows are in the tmux session `studio`
# (tmux attach -t studio). Nothing lands (auto_land = false) and nothing is picked from GitHub (feed = false).
set -eu
cd "$(dirname "$0")/.."
via=anthropic; case "${1:-}" in openrouter|anthropic) via=$1; shift ;; esac
[ $# -gt 0 ] || set -- 6214 6100
PY=${PY:-../integration/.venv/bin/python}   # the runner's python must import the MCP SDK
export PYTHONPATH=.
case "$via" in
  openrouter) [ -s ~/.config/openrouter/key ] || { echo "no OpenRouter key file"; exit 1; }
              coder=anthropic/claude-sonnet-5.5; [ "${CODER:-}" = haiku ] && coder=anthropic/claude-haiku-5.5; reviewer=1; provider=openrouter ;;
  anthropic)  [ -s ~/.config/anthropic/key ] || [ -s ~/.config/anthropic/key-lane ] || { echo "no Anthropic key file"; exit 1; }
              coder=claude-sonnet-5-5; [ "${CODER:-}" = haiku ] && coder=claude-haiku-5-5; reviewer=0; provider=anthropic ;;
  *) echo "openrouter or anthropic"; exit 1 ;;
esac
# ONE builder works the whole lane in one window; near 85 % of the (trial-small) context it writes its own note and a
# successor takes the rest in the same worktree. The checks run per issue as each is done.
"$PY" -m pipeline start "$@" --task studio-lane --from-file pipeline/studio-issues --provider "$provider" --model "$coder"
for n in "$@"; do
  "$PY" -m pipeline review "$n@studio-lane" --worker "$reviewer" || echo "$n: not reviewed (checks not green, or the reviewer stopped)"
done
"$PY" -m pipeline status | head -40
"$PY" -m pipeline run-log      # studio-run-log.tsv and studio-handoff-log.tsv in agent-work/status/briefs
