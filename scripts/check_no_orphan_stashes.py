#!/usr/bin/env python3
"""Pins `git.commit-never-stash` (spec: git-worktree-workflow): the shared stash stack's
size only ever shrinks deliberately.

READ-ONLY: this script never runs a mutating git command (no `stash pop`/`stash drop`/
`stash clear`). It only calls `git stash list`.

The shared stash stack (`~/code/fichero/.git`, common to every worktree) is NOT expected to
be empty — it holds long-lived entries that belong to the maintainer, parked on purpose. So
this is a SHRINK-ONLY CEILING, same shape as `scripts/spec_pipeline_baseline.json`:
`scripts/stash_ceiling.json` records the current count. `git stash list` growing past that
ceiling means someone left a NEW stash instead of a WIP commit (the discipline this pins) —
fail loud and name the newest entries so whoever added one can find it. `git stash list`
shrinking below the ceiling means an entry was resolved and the ceiling itself must be
lowered (`--update-ceiling`), the same ratchet direction as every other baseline in this
repo — never silently absorbed. `--update-ceiling` is LOWER-ONLY (plus first-time seeding
when no ceiling file exists yet): it refuses (exit 2) to write a HIGHER count than what is
already stored, because that would be the exact escape hatch this check exists to close — a
worker who left a stash could otherwise just run it and go green. Raising the ceiling is a
maintainer decision made by hand-editing `scripts/stash_ceiling.json` with a reason, never
this script's job.

Run:
    python scripts/check_no_orphan_stashes.py
    python scripts/check_no_orphan_stashes.py --update-ceiling
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

CEILING_PATH = pathlib.Path("scripts/stash_ceiling.json")


def _git_stash_list() -> list[str]:
    """The shared stash stack, one entry per line. Read-only — `git stash list` never
    mutates anything."""
    proc = subprocess.run(
        ["git", "stash", "list"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(f"FAIL check_no_orphan_stashes: `git stash list` exited {proc.returncode}: "
              f"{proc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _git_stash_list_named() -> str:
    """The newest entries, named, for a human to find the offender. Read-only."""
    proc = subprocess.run(
        ["git", "stash", "list", "--format=%gd %cr %gs"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return "(could not list stash entries by name)"
    return proc.stdout


def _load_ceiling() -> int:
    if not CEILING_PATH.exists():
        print(f"FAIL check_no_orphan_stashes: {CEILING_PATH} does not exist — "
              f"run --update-ceiling once to seed it.", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(CEILING_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL check_no_orphan_stashes: {CEILING_PATH} is malformed JSON: {exc}",
              file=sys.stderr)
        sys.exit(2)
    ceiling = data.get("ceiling")
    if not isinstance(ceiling, int):
        print(f"FAIL check_no_orphan_stashes: {CEILING_PATH} has no integer `ceiling` field",
              file=sys.stderr)
        sys.exit(2)
    return ceiling


def _write_ceiling(count: int, reason: str) -> None:
    CEILING_PATH.write_text(
        json.dumps({"ceiling": count, "reason": reason}, indent=2) + "\n", encoding="utf-8"
    )


def check() -> int:
    entries = _git_stash_list()
    count = len(entries)
    ceiling = _load_ceiling()

    if count > ceiling:
        print(
            f"FAIL check_no_orphan_stashes: git stash list has {count} entries, above the "
            f"ceiling of {ceiling} in {CEILING_PATH} — a bare `git stash` was left instead "
            f"of a WIP commit (git.commit-never-stash). Newest entries:\n"
            f"{_git_stash_list_named()}"
        )
        return 1
    if count < ceiling:
        print(
            f"FAIL check_no_orphan_stashes: git stash list has {count} entries, below the "
            f"ceiling of {ceiling} in {CEILING_PATH} — lower the ceiling deliberately "
            f"(run --update-ceiling) rather than leaving stale headroom."
        )
        return 1
    print(f"OK check_no_orphan_stashes: {count} stash entries, matches the ceiling.")
    return 0


def update_ceiling() -> int:
    """LOWER-ONLY, except for first-time seeding. Raising the ceiling is the one thing this
    script must never do automatically — that's precisely the escape hatch the check exists
    to close (a worker who stashed could otherwise just run this and go green). Seeding a
    brand-new ceiling file (none exists yet) is the one exception: there is no ceiling to
    raise past."""
    entries = _git_stash_list()
    count = len(entries)
    if not CEILING_PATH.exists():
        _write_ceiling(count, "current count of the maintainer's long-lived stash entries")
        print(f"OK check_no_orphan_stashes --update-ceiling: seeded {count} to {CEILING_PATH}.")
        return 0
    current_ceiling = _load_ceiling()
    if count > current_ceiling:
        print(
            f"FAIL check_no_orphan_stashes --update-ceiling: current count ({count}) is ABOVE "
            f"the stored ceiling ({current_ceiling}) — refusing to raise it automatically. "
            f"Raising the ceiling is a maintainer decision: hand-edit {CEILING_PATH} with a "
            f"reason.",
            file=sys.stderr,
        )
        return 2
    if count == current_ceiling:
        print(f"OK check_no_orphan_stashes --update-ceiling: count ({count}) already matches "
              f"the ceiling — no-op.")
        return 0
    _write_ceiling(count, "lowered after resolving stash entries")
    print(f"OK check_no_orphan_stashes --update-ceiling: lowered {current_ceiling} -> {count} "
          f"in {CEILING_PATH}.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--update-ceiling":
        return update_ceiling()
    if len(argv) != 1:
        print("usage: python scripts/check_no_orphan_stashes.py [--update-ceiling]", file=sys.stderr)
        return 2
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
