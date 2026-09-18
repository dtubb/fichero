"""Pins the two `git-worktree-workflow.md` behaviors that are actually source-inspectable
(spec: git-worktree-workflow). The other five behaviors in that spec are operational
conventions about how a human/agent uses git day to day (never `git stash`, clean up merged
worktrees, pull work from GitHub milestones) — nothing in the repo tree proves or disproves
those, so they are not pinned here; see the spec's own note on why.
"""
from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SPAWN_WORKER = REPO_ROOT / "scripts" / "spawn-worker.sh"


def test_spawn_worker_fetches_origin_before_creating_the_worktree():
    """git.branch-off-origin-main: `spawn-worker.sh` must fetch `origin` before it creates
    the worktree, so the branch point is fresh `origin/main`, not a possibly-stale local
    `main`."""
    text = SPAWN_WORKER.read_text(encoding="utf-8")
    fetch_match = re.search(r"git\s+.*fetch\s+origin", text)
    worktree_add_match = re.search(r"git\s+.*worktree add", text)
    assert fetch_match, "spawn-worker.sh no longer fetches origin"
    assert worktree_add_match, "spawn-worker.sh no longer creates a worktree"
    assert fetch_match.start() < worktree_add_match.start(), (
        "spawn-worker.sh must fetch origin BEFORE creating the worktree, not after"
    )
    assert "origin/main" in text, "the worktree must branch off origin/main, not local main"


def test_no_shell_script_hardcodes_the_canonical_venv_path():
    """git.shared-venv: no `scripts/*.sh` may hard-code the canonical checkout's absolute
    venv path — every worktree resolves its own tree via `PYTHONPATH`, never a baked-in
    `~/code/fichero/.venv`."""
    offenders = []
    for path in (REPO_ROOT / "scripts").glob("*.sh"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "code/fichero/.venv" in text or "code/fichero/.venv".replace("/", "\\/") in text:
            offenders.append(path.name)
    assert not offenders, f"scripts hard-coding the canonical venv path: {offenders}"
