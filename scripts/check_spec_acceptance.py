#!/usr/bin/env python3
"""A behaviour's acceptance text is the owner's: a batch changes it only with a `Spec-change:` trailer naming the ruling.

Why (review rounds 2026-11-03..05, presubmit lint 2 of the six): seven NOT READY verdicts were acceptance lines rewritten to match the code
("undoable" to "not on the undo stack", a field renamed, a Tests list replaced, an [OK] flip whose line still named an unmet condition).

For every behaviour bullet in a spec file the batch changes (against `git merge-base HEAD origin/integration`; `FICHERO_SPEC_BASE`
overrides) that exists at the base, the ACCEPTANCE TEXT is compared: the bullet with its status tags (`[GAP]`, `[PARTIAL]`, `[OK]`,
`[BROKEN]`), its issue numbers (`#1234`) and its cited paths removed, cut at its first note (`Built`, `Not built`, `Was`, `Not yet`,
`Tests:`/`Test:`). The free edits (manager 2026-11-04) are exactly those: a tag, an issue number, an appended note, the test paths. Any
other change to that text, or a bullet deleted, FAILS with the bullet's line, unless a commit in the batch carries a trailer
`Spec-change: <what and why, naming the owner's or the manager's ruling>`.

Run: python scripts/check_spec_acceptance.py [ROOT]
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

SPECS = "docs/contributor_manual/specs"
BULLET = re.compile(r"^- `([a-z0-9][\w.-]+)`")
NOTE = re.compile(r"\*\*(?:Built|Not built|Was|Not yet)\b|\b(?:Built|Not built|Was|Not yet)\b\**:|\b(?:Built|Not built)\**\s+\d{4}-\d\d-\d\d|\bTests?(?: \(to write\))?:", re.I)
TAG = re.compile(r"\*{0,2}\[(?:GAP|PARTIAL|OK|BROKEN|MISSING|PROPOSED)(?:/[A-Z]+)?\]\*{0,2}")
ISSUE = re.compile(r"#\d{2,6}")
LEAD = re.compile(r"^\s*(?:—\s*)?(?:\*{0,2}\[[^\]]*\]\*{0,2}\s*)?(?:\(.*?\)\s*(?=—|:|$))?")
CITED = re.compile(r"`[^`]*(?:/|::)[^`]*`")
TRAILER = re.compile(r"^Spec-change: .*\b(?:owner|manager)\b", re.M | re.I)


def _git(root, *a) -> str:
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def bullets(text: str) -> dict[str, tuple[int, str]]:
    """{id: (1-based line, the bullet's text joined)} for every behaviour bullet."""
    lines, out, i = text.splitlines(), {}, 0
    while i < len(lines):
        m = BULLET.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].startswith("  ") and not BULLET.match(lines[j]):
            j += 1
        out.setdefault(m.group(1), (i + 1, " ".join(x.strip() for x in lines[i:j])))
        i = j
    return out


def acceptance(text: str) -> str:
    """The text a batch may not change: before the first note, with tags, issue numbers and cited paths taken out."""
    body = text.split("`", 2)[2] if text.startswith("- `") else text  # past the id
    body = LEAD.sub("", body, count=1)  # the tag and its parenthetical (issues, who ruled, why): metadata, not acceptance
    if m := NOTE.search(body):
        body = body[:m.start()]
    body = CITED.sub("", ISSUE.sub("", TAG.sub("", body)))
    return re.sub(r"[\s();,.*—-]+", " ", body).strip().lower()


def check(root: pathlib.Path) -> list[str]:
    if not (root / SPECS).is_dir():
        return [f"no specs dir at {root / SPECS}: nothing was read"]  # a moved tree must never read as clean (#4382)
    base = os.environ.get("FICHERO_SPEC_BASE") or _git(root, "merge-base", "HEAD", "origin/integration").strip()
    if not base:
        return []  # the land branch itself: nothing to compare
    if TRAILER.search(_git(root, "log", "--format=%B", f"{base}..HEAD")):
        return []  # the batch says what changed and whose ruling it is: the reviewer reads it
    fails = []
    for rel in _git(root, "diff", "--no-ext-diff", "--name-only", base, "HEAD", "--", f"{SPECS}/*.md").split():
        old = bullets(_git(root, "show", f"{base}:{rel}"))
        new = bullets((root / rel).read_text(encoding="utf-8")) if (root / rel).is_file() else {}
        for bid, (_n, text) in old.items():
            if bid not in new:
                fails.append(f"{rel}: behaviour `{bid}` was deleted: restore it, or add a `Spec-change:` trailer naming the ruling")
            elif acceptance(new[bid][1]) != acceptance(text):
                fails.append(f"{rel}:{new[bid][0]}: `{bid}`'s acceptance text changed (only its tag, issue numbers, test paths and appended "
                             f"Built / Not built / Was notes are free): restore it, or add a `Spec-change:` trailer naming the ruling")
    return fails


def main() -> int:
    fails = check(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
    for f in fails:
        print(f"FAIL: {f}")
    print(f"check_spec_acceptance: {len(fails)} problem(s)" if fails else "check_spec_acceptance: OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
