#!/bin/bash
# The stage 0 dry run: every harness scenario against a scripted fake model, real Pi in tmux, no key, no cost, no GitHub.
# Exits non-zero on any failed scenario. Repeat it on every runner change. usage: pipeline/dry.sh [pytest args]
set -eu
cd "$(dirname "$0")/.."
PY=${PY:-../integration/.venv/bin/python}   # the runner's python must import the MCP SDK
PIPELINE_DRY=1 PYTHONPATH=. exec "$PY" -m pytest -q -p no:cacheprovider pipeline/tests/test_dry.py "$@"
