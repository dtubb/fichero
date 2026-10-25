"""The dev pipeline runner (spec: docs/contributor_manual/specs/harness/deterministic-conductor.md, #6116).

One state machine per item, an append-only journal, and three faces (CLI, MCP, local page) over the
same functions in `core.API`. Stdlib only, plus the `git`, `gh`, `pi` and `tmux` CLIs.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PIPELINE_ROOT") or Path(__file__).resolve().parent.parent)
# The journal, sessions, briefs and locks live OUTSIDE every worktree, in a path the worker's env does not carry
# (pipeline.jailed-agent): ~/.local/state/pipeline/<runner checkout name>/ unless PIPELINE_STATE says otherwise.
STATE = Path(os.environ.get("PIPELINE_STATE") or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
             / "pipeline" / ROOT.name)
