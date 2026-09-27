"""Every `scripts/check_*.py` must pass on the real tree — enforced where people actually look.

A guard nobody runs is the same failure as a guard that asks the wrong question. The SwiftLint
ratchet was set at a real 123 warnings on 2026-09-05 and the count reached 186 by 2026-09-27
with nothing stopping it (#4861: "'gate unit' never runs lint"). The guard was correct. It was
wired only into `verify_all.sh --fast`'s loop, and what lanes and the manager actually run is
this pytest suite, where a guard is enforced only if somebody happened to write a "passes on
the repo" test for it. On 2026-09-27 four guards were red on the real tree with this suite
green: the SwiftLint ratchet, preview coverage, specs-have-tests and undo coverage.

So one node per guard, run as the gate runs it (a subprocess from the repo root). A new guard
is enforced the moment it exists. A known-red guard is listed in
known_specification_failures.txt under its issue, never skipped here.
"""
from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
GUARDS = sorted(p.name for p in (ROOT / "scripts").glob("check_*.py"))

#: Guards that judge THIS MACHINE'S git state, not the tree, so a clean checkout of a good
#: commit can fail them. verify_all.sh skips check_unmerged_work for the same reason.
MACHINE_STATE = {
    "check_unmerged_work.py": "lists other lanes' unmerged branches and worktrees on this machine",
    "check_no_orphan_stashes.py": "reads the stash stack shared by every worktree on this machine",
    "check_merged_worktrees.py": "lists this machine's worktrees whose branch already landed",
}


@pytest.fixture(scope="module")
def results() -> dict[str, subprocess.CompletedProcess]:
    """Run them all once, concurrently — serially they take over two minutes."""
    def run(name: str) -> tuple[str, subprocess.CompletedProcess]:
        return name, subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name)],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
    to_run = [g for g in GUARDS if g not in MACHINE_STATE]
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(run, to_run))


def test_the_inventory_is_not_empty():
    """If the glob found nothing, every parametrized node below would vanish silently."""
    assert len(GUARDS) > 50


@pytest.mark.parametrize("guard", [g for g in GUARDS if g not in MACHINE_STATE])
def test_every_guard_passes_on_the_real_tree(guard, results):
    result = results[guard]
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-25:])
    assert result.returncode == 0, f"{guard} exited {result.returncode}:\n{tail}"
