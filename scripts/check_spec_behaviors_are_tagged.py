#!/usr/bin/env python3
"""Every behavior bullet in a spec carries a state tag, or the pipeline cannot see it.

Found twice on 2026-09-27, the same way both times:

  * `segments-and-geometry.md:190-202` describes tables and cells in detail -- a table is a
    segment, cells carry row/column/span/header, an account book or census return "becomes a
    real table" -- and there is not ONE `source.table.*` behavior. (#5120)
  * `segment-representations.md` has 21 behavior-shaped bullets; `spec_pipeline status`
    reports 12. Nine are invisible.

An untagged bullet is the worst kind of spec debt because it reads as covered. It cannot be
[OK], cannot cite a test, never appears in the queue and never burns down -- it is prose
wearing a behavior's clothes. Tagging it [GAP] costs one word and immediately tells the
truth.

Shrink-only, like its siblings: today's 100-odd untagged bullets are baselined so this is a
ratchet rather than a wall. A NEW untagged bullet fails; a baselined one that gets tagged
must be removed from the baseline (a fixed-but-still-listed entry fails too, so the file
cannot rot).

    python scripts/check_spec_behaviors_are_tagged.py
    python scripts/check_spec_behaviors_are_tagged.py --update-baseline
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "docs/contributor_manual/specs"
BASELINE = REPO_ROOT / "scripts/spec_untagged_behaviors_baseline.json"

# Reuse the canonical block parser rather than writing a second one that drifts from it.
# check_spec_broken_has_issue.py owns the definition of "a behavior line and its block";
# a guard that re-derived it would disagree with the pipeline on exactly the edge cases
# this check exists to catch.
_SRC = REPO_ROOT / "scripts/check_spec_broken_has_issue.py"
_SPEC = importlib.util.spec_from_file_location("_spec_broken", _SRC)
assert _SPEC and _SPEC.loader
_broken = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _broken
_SPEC.loader.exec_module(_broken)

# Every tag the pipeline recognises -- kept identical to spec_pipeline.TAG_RE_ALL, including
# its `\*{0,2}`, because specs legitimately write both `**[GAP]**` and `[GAP]`.
TAG_RE_ALL = re.compile(
    r"\*{0,2}\[(OK|BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING|PROPOSED|CONVENTION)[^\]]*\]\*{0,2}"
)

# A dotted lowercase identifier in a bullet is USUALLY a behavior id, but not always: specs
# also open bullets with a filename or a module path. Those are prose, not behaviors, and
# demanding a state tag on them would be noise the next reader learns to ignore.
_FILE_SUFFIXES = (".py", ".swift", ".sh", ".json", ".xml", ".md", ".yml", ".yaml", ".xcconfig")
_MODULE_PREFIXES = ("fichero_server.", "fichero.", "fichero_cli.")


def is_behavior_id(identifier: str) -> bool:
    """A behavior id, not a filename or an importable module path."""
    if identifier.endswith(_FILE_SUFFIXES):
        return False
    return not identifier.startswith(_MODULE_PREFIXES)


def untagged_behaviors(specs_dir: pathlib.Path) -> list[tuple[str, int, str]]:
    """Every behavior bullet carrying no state tag, as (spec path, line, id)."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(specs_dir.rglob("*.md")):
        if path.name.startswith("_"):  # _TEMPLATE.md and friends are scaffolding
            continue
        # Hidden directories are never specs, and one of them is dangerous: an agent's
        # isolated worktree lands at `<its cwd>/.claude/worktrees/<id>/`, a FULL second copy
        # of the repo. On 2026-09-27 one was spawned from inside specs/source/, and this scan
        # walked into it and reported every bullet of every markdown file in the repo. git
        # ignores `.claude/`; a filesystem walk does not, so the walk has to.
        if any(part.startswith(".") for part in path.relative_to(specs_dir).parts[:-1]):
            continue
        # Repo-relative for a real spec so the message is a path you can click; relative to
        # the scanned root otherwise, so a fixture directory outside the repo still works
        # (the tests found this by raising ValueError here on their first run).
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.relative_to(specs_dir).as_posix()
        for line_no, behavior_id, block in _broken._iter_behavior_blocks(
            path.read_text().splitlines()
        ):
            if not is_behavior_id(behavior_id):
                continue
            if not TAG_RE_ALL.search(block):
                found.append((rel, line_no, behavior_id))
    return found


def _key(entry: tuple[str, int, str]) -> str:
    """Identity WITHOUT the line number -- editing prose above a bullet must not fail it."""
    path, _line, behavior_id = entry
    return f"{path}::{behavior_id}"


def _load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text())["untagged"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    if not SPECS_DIR.exists():
        print(f"FAIL check_spec_behaviors_are_tagged: no specs at {SPECS_DIR} (blind, not green)")
        return 2

    found = untagged_behaviors(SPECS_DIR)
    current = {_key(e) for e in found}

    if args.update_baseline:
        BASELINE.write_text(json.dumps({"untagged": sorted(current)}, indent=2) + "\n")
        print(f"baseline updated: {len(current)} untagged behavior(s)")
        return 0

    baseline = _load_baseline()
    new = [e for e in found if _key(e) not in baseline]
    fixed = sorted(baseline - current)

    if not new and not fixed:
        print(
            f"OK check_spec_behaviors_are_tagged: every behavior bullet outside the "
            f"{len(baseline)}-entry baseline carries a state tag"
        )
        return 0

    for path, line, behavior_id in new:
        print(
            f"FAIL {path}:{line}: `{behavior_id}` has no state tag. The pipeline cannot see "
            f"it, so it can never be [OK], never cite a test and never burn down. Tag it "
            f"[GAP] (or whatever is true) -- one word, and it starts telling the truth."
        )
    for key in fixed:
        print(
            f"FAIL {key} is in {BASELINE.name} but is now tagged. Remove that line: the "
            f"baseline shrinks only, so a fixed-but-still-listed entry keeps it honest."
        )
    print(
        f"FAIL check_spec_behaviors_are_tagged: {len(new)} new untagged, "
        f"{len(fixed)} baselined-but-fixed."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
