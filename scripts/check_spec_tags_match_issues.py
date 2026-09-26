#!/usr/bin/env python3
"""Fail when a spec behaviour tagged broken cites only CLOSED issues.

The third side of a triangle whose other two are already guarded:

    check_spec_broken_has_issue.py   every [BROKEN]/[GAP] behaviour CITES an issue
    check_closed_issues_landed.py    every closed issue is backed by a PUSHED commit
    (this)                           every [BROKEN]/[GAP] behaviour's issue is OPEN

Nothing closed the loop, and it drifted twice in one day (2026-09-26).
`kg-readable-representation.md` still tagged `kg.read.aggregation-never-crosses-languages`
and `kg.read.every-sentence-sourced` as [BROKEN] against #4839 and #4840 — both fixed
weeks earlier, both verified, both closed. A third, `kg.read.aggregation-keeps-objects`,
was the same and nobody had even noticed it.

Why that costs more than tidiness. A spec is the thing this project builds from: work is
chosen by reading which behaviours are broken. A behaviour that says it is broken when it
works sends someone to fix what is already fixed — and the cost is silent, because they
find working code and conclude they misread the spec, not that the spec is wrong.

A failure here means ONE of two things, and the check cannot tell which — deliberately,
because both need a person:

  * the TAG is stale — the work landed, retag to [OK] and cite the tests that prove it; or
  * the ISSUE was closed too early — reopen it, because the spec still says it is broken.

Exit codes:
    0  every broken-tagged behaviour cites at least one OPEN issue
    1  at least one cites only closed issues
    2  BLIND: could not read a spec, or could not reach GitHub. NEVER reported as a pass.

Usage:
    check_spec_tags_match_issues.py [--specs-root docs/contributor_manual/specs]
    check_spec_tags_match_issues.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BROKEN_TAGS = ("[BROKEN]", "[GAP]", "[PARTIAL]", "[MISSING]")
ISSUE_RE = re.compile(r"#(\d{3,6})")
# A behaviour line names a backtick-quoted id and carries a tag. Continuation
# lines are indented and belong to the behaviour above them.
BEHAVIOUR_RE = re.compile(r"^\s*[-*]\s+`([a-z0-9][a-z0-9._-]*)`")


class Blind(Exception):
    """An input could not be read. The check has gone blind; it has not passed."""


def behaviours_with_issues(path: Path) -> list[tuple[str, int, set[int]]]:
    """Every broken-tagged behaviour in `path`, with the issues it cites.

    Issues on indented continuation lines count — `check_spec_broken_has_issue.py`
    accepts them there, so this must too, or the two guards would disagree about
    what citing an issue means.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Blind(f"cannot read {path}: {exc}") from exc

    found: list[tuple[str, int, set[int]]] = []
    current: tuple[str, int] | None = None
    tagged = False
    issues: set[int] = set()

    def flush() -> None:
        if current and tagged:
            found.append((current[0], current[1], set(issues)))

    for number, line in enumerate(lines, start=1):
        match = BEHAVIOUR_RE.match(line)
        if match:
            flush()
            current = (match.group(1), number)
            tagged = any(t in line for t in BROKEN_TAGS)
            issues = {int(n) for n in ISSUE_RE.findall(line)}
        elif current and (line.startswith((" ", "\t")) or not line.strip()):
            if any(t in line for t in BROKEN_TAGS):
                tagged = True
            issues.update(int(n) for n in ISSUE_RE.findall(line))
        else:
            flush()
            current, tagged, issues = None, False, set()
    flush()
    return found


def issue_states(numbers: set[int]) -> dict[int, str]:
    """OPEN/CLOSED per issue, from `gh`. Unreachable GitHub is BLIND, not empty.

    ONE bulk listing, not one call per issue. The first version made 465 separate
    requests and took minutes — and a guard slow enough to skip is a guard nobody
    runs, which is the same end state as not having one.
    """
    if not numbers:
        return {}
    result = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "5000",
         "--json", "number,state"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise Blind(f"cannot list issues from GitHub: {result.stderr.strip()[:200]}")
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Blind(f"cannot parse the issue listing: {exc}") from exc
    if not rows:
        raise Blind("GitHub returned no issues at all — refusing to call every tag stale")

    known = {int(r["number"]): str(r["state"]).upper() for r in rows}
    # An issue the listing does not mention is MISSING, not assumed open. Saying
    # "I could not find it" is honest; assuming open would hide a deleted or
    # transferred issue behind a passing check.
    return {n: known.get(n, "MISSING") for n in numbers}


def check(specs_root: Path, *, _states=issue_states) -> int:
    specs = sorted(specs_root.rglob("*.md"))
    if not specs:
        raise Blind(f"no spec files under {specs_root} — refusing to report success on nothing")

    per_file = {path: behaviours_with_issues(path) for path in specs}
    cited = {n for rows in per_file.values() for _, _, issues in rows for n in issues}
    states = _states(cited)

    stale: list[str] = []
    for path, rows in per_file.items():
        for behaviour, line_number, issues in rows:
            if not issues:
                continue  # check_spec_broken_has_issue.py owns the no-issue case
            if any(states.get(n) == "OPEN" for n in issues):
                continue
            shown = ", ".join(
                f"#{n} {states.get(n, 'UNKNOWN')}" for n in sorted(issues)
            )
            stale.append(
                f"{path}:{line_number}  `{behaviour}` is tagged broken but cites only {shown}"
            )

    print(f"scanned {len(specs)} spec files, {len(cited)} cited issues")
    if not stale:
        print("every broken-tagged behaviour cites an open issue.")
        return 0

    print(f"\n{len(stale)} behaviour(s) tagged broken with no open issue:\n")
    for row in stale:
        print(f"  {row}")
    print(
        "\nEach is ONE of two things, and this check cannot tell which:\n"
        "  * the TAG is stale — retag to [OK] and cite the tests that prove it; or\n"
        "  * the ISSUE was closed too early — reopen it, because the spec still\n"
        "    says the behaviour is broken.\n"
        "Both need a person. Do not silence this by deleting the issue reference."
    )
    return 1


def self_test() -> int:
    """Synthesised specs, never borrowed from the real tree — which could shrink
    to nothing and make every assertion here vacuously true."""
    failures: list[str] = []

    def case(name: str, ok: bool) -> None:
        print(f"  {'✓' if ok else '✗'} {name}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.md").write_text(
            "- `thing.that.works` — **[OK]** built and tested\n"
            "- `thing.that.is.broken` — **[BROKEN]** not built yet (#111)\n"
        )
        case("an open issue passes", check(root, _states=lambda n: {111: "OPEN"}) == 0)
        case("a closed issue FAILS", check(root, _states=lambda n: {111: "CLOSED"}) == 1)

        (root / "b.md").write_text(
            "- `spread.over.lines` — **[GAP]**\n  more prose about it (#222)\n"
        )
        case(
            "an issue on a continuation line is seen",
            check(root, _states=lambda n: {111: "OPEN", 222: "CLOSED"}) == 1,
        )

        (root / "c.md").write_text("- `ok.only` — **[OK]** fine (#333)\n")
        case(
            "an [OK] behaviour citing a closed issue is NOT flagged",
            check(root, _states=lambda n: {111: "OPEN", 222: "OPEN", 333: "CLOSED"}) == 0,
        )

        blind = False
        try:
            check(root / "nonexistent", _states=lambda n: {})
        except Blind:
            blind = True
        case("an empty specs root goes BLIND, not pass", blind)

        blind = False
        try:
            def unreachable(_numbers):
                raise Blind("simulated: GitHub unreachable")
            check(root, _states=unreachable)
        except Blind:
            blind = True
        case("unreachable GitHub goes BLIND, not pass", blind)

    if failures:
        print(f"\nself-test FAILED: {', '.join(failures)}")
        return 1
    print("\nself-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs-root", default="docs/contributor_manual/specs", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    try:
        return check(args.specs_root)
    except Blind as exc:
        print(f"BLIND: {exc}", file=sys.stderr)
        print("Refusing to report success on input I could not read.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
