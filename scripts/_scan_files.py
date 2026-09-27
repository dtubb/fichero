"""scan_rglob — `Path.rglob` for guardrails, minus hidden directories below the root.

An agent spawned with worktree isolation gets `<cwd>/.claude/worktrees/<id>/`, a FULL
copy of the repository, created wherever that agent's cwd was. git ignores `.claude/`;
`rglob` does not. So every guard that walked a tree containing one scanned the whole
repository twice: on 2026-09-27 a worktree under `docs/contributor_manual/specs/source/`
gave `check_spec_behaviors_are_tagged` 128 bogus findings, and 70-odd other guards were
exposed the same way. A guard reporting another checkout's files is reporting nothing
true about this one — and a copy that is CLEAN hides nothing but still doubles counts
and scan floors.

The rule is "no hidden directory BELOW the scan root", not "no `.claude`": a guard's
source roots (`fichero/fichero`, `fichero-server/src`, `docs/`) hold no hidden source
directories, and `.git`, `.build`, `.swiftpm` and `.pytest_cache` are all things a
source scan should not read either. The root itself may be hidden or sit inside one —
this very module runs from a worktree under `.claude/` — so only path parts BELOW the
root are judged.

Hidden FILES are still yielded, as `Path.rglob` yields them; only directories are pruned,
and pruned before descent, so a nested copy costs nothing to skip.
"""
from __future__ import annotations

import os
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterator


def scan_rglob(
    root: Path | str, pattern: str = "*", *, optional: bool = False
) -> Iterator[Path]:
    """Like `Path(root).rglob(pattern)`, but never descends into a hidden directory.

    A MISSING root raises, where `Path.rglob` returns nothing. An empty walk over a path
    that does not exist is the other way a scan reads clean while looking at nothing: a
    test computed its root with `parents[4]` (one level too high), searched no files, and
    its absence assertion passed on 2026-09-27. Pass `optional=True` only for a root that
    may legitimately not exist in a checkout, and say why at the call site.
    """
    root = Path(root)
    if not root.is_dir():
        if optional:
            return
        raise FileNotFoundError(f"scan root does not exist (a walk of it would find nothing): {root}")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        base = Path(dirpath)
        for name in (*dirnames, *filenames):
            if fnmatchcase(name, pattern):
                yield base / name
