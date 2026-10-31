#!/bin/bash
# Studio trial, stage 1: the named items through the runner and Pi (Haiku 5.5 codes, Sonnet 5.5 reviews).
# usage: pipeline/studio-stage1.sh openrouter|anthropic [issue ...]      default items: 6214 6100
# openrouter: both models via OpenRouter, pinned to the Anthropic endpoint (the OpenRouter key in ~/.config/openrouter/).
# anthropic: direct, with the Anthropic key in ~/.config/anthropic/.
# Spends real money (est. US$0.3-1 for two items; the daily cap is 10). Windows are in the tmux session `studio`
# (tmux attach -t studio). Nothing lands (auto_land = false) and nothing is picked from GitHub (feed = false).
set -eu
cd "$(dirname "$0")/.."
via=${1:?usage: studio-stage1.sh openrouter|anthropic [issue ...]}; shift
[ $# -gt 0 ] || set -- 6214 6100
PY=${PY:-../integration/.venv/bin/python}   # the runner's python must import the MCP SDK
export PYTHONPATH=.
case "$via" in
  openrouter) [ -s ~/.config/openrouter/key ] || { echo "no OpenRouter key file"; exit 1; }
              coder=anthropic/claude-haiku-5.5; reviewer=1; provider=openrouter ;;
  anthropic)  [ -s ~/.config/anthropic/key ] || [ -s ~/.config/anthropic/key-lane ] || { echo "no Anthropic key file"; exit 1; }
              coder=claude-haiku-5-5; reviewer=0; provider=anthropic ;;
  *) echo "openrouter or anthropic"; exit 1 ;;
esac
for n in "$@"; do
  "$PY" -m pipeline start "$n" --task "studio-$n" --from-file "pipeline/studio-issues/$n.json" --provider "$provider" --model "$coder"
done
for n in "$@"; do
  "$PY" -m pipeline review "$n@studio-$n" --worker "$reviewer" || echo "$n: not reviewed (checks not green, or the reviewer stopped)"
done
"$PY" -m pipeline status | head -40
"$PY" -m pipeline run-log      # agent-work/status/briefs/studio-run-log.tsv
