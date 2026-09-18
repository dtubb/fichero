#!/usr/bin/env python3
"""Every [BROKEN]/[GAP]/[PARTIAL]/[MISSING] spec behavior must cite a tracking issue.

The rule (creative director, 2026-09-18): a spec behavior tagged broken/gap/partial/missing
is fine to leave broken for now, but it MUST have an issue, and issues get worked. A behavior
line looks like:

    - `panes.split.asymmetric` — **[GAP/BROKEN]** text describing the gap…
      continuation lines are indented and belong to the same behavior.

The line (or one of its indented continuation lines) must contain either an issue reference
(`#1234`) or a superseding pointer to another tracked epic increment (`→ #1234`). [OK] lines
are never checked — they are not broken.

Pre-existing debt in files not yet triaged for this rule is tracked, not hidden: see
GRANDFATHERED_FILES below (modeled on scripts/check_spec_milestones.py's grandfather list).

Run: python scripts/check_spec_broken_has_issue.py
"""

from __future__ import annotations

import pathlib
import re
import sys

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")

# Specs with untracked broken/gap behaviors as of the 2026-09-18 rule rollout. Their debt is
# reported (a count) but does NOT fail the gate — it is worked down file by file (creative
# director, 2026-09-18: kg/* first, then testing/*, docs/*, transport/*). Remove a path here
# the moment its last untracked behavior gets an issue — a file that is already clean MUST
# NOT stay in this set (this guardrail enforces that itself: see `_check_grandfather_is_live`),
# so the list can only shrink. Do NOT add new files here — new debt must ship with an issue.
GRANDFATHERED_FILES = {
    "docs/docs-citations-bibliography.md",
    "transport/transport-http-uds.md",
}

# A behavior id is a dotted lowercase token: e.g. `panes.split.asymmetric`,
# `nodeconfig.fields.entities.prompt`, `m2p.library-is-always-navigator`. This excludes a
# backticked FILE PATH (contains "/", e.g. `agent-work/reviews/2026-08-02-....md`) and a
# backticked Swift/Python SYMBOL name (starts uppercase, e.g. `ChatView`, or has no dot).
BEHAVIOR_ID_RE = r"[a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+"
BEHAVIOR_START_RE = re.compile(r"^(\s*)-\s+`(" + BEHAVIOR_ID_RE + r")`")
TAG_RE = re.compile(r"\*{0,2}\[(BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING)[^\]]*\]\*{0,2}")
ISSUE_RE = re.compile(r"#\d+")
CONTINUATION_RE = re.compile(r"^\s+\S")  # indented, non-blank line


def _is_scaffold(p: pathlib.Path) -> bool:
    return p.name.startswith("_")


def _spec_files() -> list[pathlib.Path]:
    if not SPECS_DIR.exists():
        return []
    return [p for p in sorted(SPECS_DIR.rglob("*.md")) if not _is_scaffold(p)]


def _iter_behavior_blocks(lines: list[str]) -> list[tuple[int, str, str]]:
    """Yield (1-indexed start line, behavior id, joined block text) for every behavior line.

    A behavior line's block runs until the NEXT behavior line (at any indentation — a nested
    sub-bullet with its own `id` tag starts its own block rather than being swallowed by its
    parent) or the first non-continuation (blank / dedented non-list) line, whichever is first.
    """
    blocks: list[tuple[int, str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        m = BEHAVIOR_START_RE.match(lines[i])
        if not m:
            i += 1
            continue
        behavior_id = m.group(2)
        block_lines = [lines[i]]
        j = i + 1
        while j < n and CONTINUATION_RE.match(lines[j]) and not BEHAVIOR_START_RE.match(lines[j]):
            block_lines.append(lines[j])
            j += 1
        blocks.append((i + 1, behavior_id, "\n".join(block_lines)))
        i = j
    return blocks


def main() -> int:
    specs = _spec_files()
    if not specs:
        print(f"FAIL check_spec_broken_has_issue: no specs found under {SPECS_DIR} (blind, not green)")
        return 2

    failures: list[str] = []
    grandfathered_debt: list[str] = []
    grandfathered_seen_debt: set[str] = set()
    tagged_count = 0
    for spec in specs:
        rel = str(spec.relative_to(SPECS_DIR)).replace("\\", "/")
        text = spec.read_text(encoding="utf-8")
        lines = text.splitlines()
        for start_line, behavior_id, block in _iter_behavior_blocks(lines):
            if not TAG_RE.search(block):
                continue  # untagged / [OK] — not our concern
            tagged_count += 1
            if ISSUE_RE.search(block):
                continue
            entry = (
                f"{spec.relative_to(SPECS_DIR.parent.parent)}:{start_line}: "
                f"`{behavior_id}` is tagged broken/gap but cites no issue "
                f"(`#<digits>` or `→ #<digits>`)."
            )
            if rel in GRANDFATHERED_FILES:
                grandfathered_debt.append(entry)
                grandfathered_seen_debt.add(rel)
            else:
                failures.append(entry)

    # The grandfather list only shrinks: a file with zero remaining untracked debt must be
    # removed by whoever cleared it, or the gate blocks the false "still grandfathered" claim.
    stale_grandfather = sorted(GRANDFATHERED_FILES - grandfathered_seen_debt)
    for stale in stale_grandfather:
        failures.append(
            f"{stale}: listed in GRANDFATHERED_FILES but has zero untracked behaviors now — "
            f"remove it from the list."
        )

    if failures:
        print("FAIL check_spec_broken_has_issue:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(
        f"OK check_spec_broken_has_issue: {tagged_count} broken/gap/partial/missing behaviors "
        f"across {len(specs)} specs, all cite an issue "
        f"({len(grandfathered_debt)} grandfathered behaviors in {len(grandfathered_seen_debt)} "
        f"files not yet triaged)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
