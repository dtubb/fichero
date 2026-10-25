"""The dev pipeline runner (spec: docs/contributor_manual/specs/harness/deterministic-conductor.md, #6116).

One state machine per item, an append-only journal, and three faces (CLI, MCP, local page) over the
same functions in `core.API`. Stdlib only, plus the `git`, `gh`, `pi` and `tmux` CLIs.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PIPELINE_ROOT") or Path(__file__).resolve().parent.parent)
STATE = Path(os.environ.get("PIPELINE_STATE") or ROOT / "pipeline" / "state")
BASE = os.environ.get("PIPELINE_BASE", "origin/integration")
