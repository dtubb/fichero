#!/usr/bin/env python3
"""No spec text twice: a behaviour id defined by two bullets in one spec file, or two long lines (a bullet or a paragraph) in one
file that open with the same 150 characters, FAIL with both line numbers.

Why (review rounds 2026-11-02..04): a conflict resolution or a re-add brought back a second copy of a bullet three times (five
diverging copies of one paragraph once, the jail-home bullet twice, the presubmit bullet twice); each cost a whole ladder and a
review. A copy that diverges later still opens the same way, so the opening is the key. Under a second over every spec.

Run: python scripts/check_spec_no_duplicates.py [ROOT]
"""
from __future__ import annotations

import pathlib
import re
import sys

from _scan_files import scan_rglob

BULLET = re.compile(r"^- `([a-z0-9][\w.-]+)`\s+(?:—\s+)?\**\[")  # "- `id` [TAG]" and "- `id` — **[TAG]**"
PREFIX = 150
# Debt found when this guard landed (2026-11-04, groom issue #6353): ids defined twice in specs other lanes own. Reported, not failed; each is
# for the manager's groom batch (which copy holds the owner's acceptance text is a ruling, not a guess). The list only shrinks:
# an entry that is no longer duplicated FAILS until it is removed here, and nothing is ever added.
KNOWN = {
    ("harness/surfaces-from-openapi.md", "openapi.mcp.installed-from-the-app"),
    ("harness/surfaces-from-openapi.md", "openapi.mcp.attaches-never-starts"),
    ("harness/surfaces-from-openapi.md", "openapi.mcp.live-round-trip"),
    ("source/models-chains-and-projects.md", "source.onboard.nothing-fits-names-nearest"),
    ("source/sharing-two-macs.md", "sharing.multiuser-404-is-a-409-in-the-engine"),
    ("transport/library-sharing.md", "sharing.share-sheet-chooses-what"),
    ("ui/panes-workspaces.md", "panes.split.focused-only"),
    ("ui/panes-workspaces.md", "panes.close.this-pane-only"),
}


def problems(root: pathlib.Path, known: set = KNOWN) -> tuple[list[str], list[str]]:
    """(failures, known debt still present)."""
    out, debt, seen = [], [], set()
    specs = root / "docs/contributor_manual/specs"
    files = sorted(scan_rglob(specs, "*.md"))  # a missing specs dir raises: never a clean read of nothing
    if not files:
        return [f"no spec files under {specs}"], []
    for f in files:
        rel = f.relative_to(specs).as_posix()
        ids: dict[str, int] = {}
        starts: dict[str, int] = {}
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if m := BULLET.match(line):
                if m.group(1) in ids and (rel, m.group(1)) in known:
                    seen.add((rel, m.group(1)))
                    debt.append(f"{f.relative_to(root)}:{n}: `{m.group(1)}` defined twice (known debt)")
                elif m.group(1) in ids:
                    out.append(f"{f.relative_to(root)}:{n}: behaviour `{m.group(1)}` is defined again (first at line {ids[m.group(1)]})")
                ids.setdefault(m.group(1), n)
            key = line.strip()
            if len(key) > PREFIX * 4 // 3 and not key.startswith("|"):  # long prose only; table rows repeat by design
                if key[:PREFIX] in starts:
                    out.append(f"{f.relative_to(root)}:{n}: repeats the text that opens line {starts[key[:PREFIX]]}")
                starts.setdefault(key[:PREFIX], n)
    out += [f"KNOWN entry {f} `{i}` is no longer duplicated: remove it from KNOWN" for f, i in sorted(known - seen)]
    return out, debt


def main() -> int:
    found, debt = problems(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    for p in found:
        print(f"FAIL: {p}")
    print(f"check_spec_no_duplicates: {len(found)} duplicate(s)" if found else f"check_spec_no_duplicates: OK ({len(debt)} known)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
