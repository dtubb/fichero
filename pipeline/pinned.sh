#!/bin/bash
# Run the runner from a pinned, detached copy of this checkout's commit, so a lane that edits pipeline/ (#6214 does), or a
# merge into this checkout, cannot change the code that is running. The journal stays this checkout's own.
# usage: pipeline/pinned.sh <pipeline args>      e.g. pipeline/pinned.sh run --once
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
sha=$(git -C "$here" rev-parse --short=12 HEAD)
copy=${PIPELINE_PINNED_DIR:-$HOME/.local/state/pipeline/pinned}/$(basename "$here")-$sha
if [ ! -d "$copy" ]; then
  git -C "$here" worktree add -q --detach "$copy" "$sha"
  [ ! -e "$here/.studio-pi" ] || ln -s "$here/.studio-pi" "$copy/.studio-pi"   # gitignored, so not in the copy
fi
export PIPELINE_STATE=${PIPELINE_STATE:-$HOME/.local/state/pipeline/$(basename "$here")}
export PIPELINE_LOGS=${PIPELINE_LOGS:-$here/agent-work/status/briefs}   # the logs belong to the checkout, not to the copy
cd "$copy"
PYTHONPATH=. exec "${PY:-$here/../integration/.venv/bin/python}" -m pipeline "$@"
