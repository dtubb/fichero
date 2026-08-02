#!/usr/bin/env python3
"""A stack of tappable rows must be a `List`, not a hand-rolled VStack (#4483).

## The finding this enforces

Mapping 22 surfaces x 7 interactions for #4464 collapsed to ONE variable:

    List / Table          -> arrows, multi-select, selection-aware context
                             menus: free, and correct
    ScrollView / VStack   -> hand-rolled, or simply absent

There was no third pattern. Every hand-rolled arrow-key handler in this app
exists because something was not a `List`. So "we don't have duplicate code
paths" is not a request for a shared interaction layer -- it reduces to *use
the native container*, and the duplication lives exactly where you cannot.

## Why a script and not a convention

The convention already existed. `ArtifactListView` and `CitationListView` BOTH
carry a doc comment saying, in as many words, "Native List(selection:), NOT a
hand-rolled VStack of tappable rows." Written down twice -- and
`DocumentInspectorRelatedTab` shipped as a `VStack` of tappable rows anyway,
losing arrow keys, the focus ring and the context menu, until a lane found it
by reading (#4483).

A convention in a comment is not a mechanism. Nothing reads it. This does.

## What it detects

The conjunction, never a single signal:

    a `ForEach` whose row body carries a TAP HANDLER
    AND whose enclosing container chain has no `List` / `Table` / `Form`

Both halves are required because neither alone means anything. A `ScrollView`
is not a list of rows; a `ForEach` is not a selection surface; a tap handler on
a lone view is just a button. Together they are the `RelatedTab` shape.

Ancestors are walked to the top of the view, so `List { Section { ForEach } }`
is correctly NOT flagged -- the `List` is what matters, not the immediate
parent.

## What it does NOT see, stated plainly

The tap must appear IN the `ForEach` body. A row extracted into a helper
(`ForEach(docs) { doc in documentRow(doc) }`, with the gesture inside
`documentRow`) is invisible to this guard -- which means the library's list
and icon modes, both genuinely hand-rolled, do not appear in its output.

That is a deliberate boundary, not an oversight. Following a call into another
function is cross-function analysis, and the widened alternative -- "a file
containing both a bare stack and a tap handler somewhere" -- is exactly the
too-broad shape that condemned correct code twice today. A guard that fires on
the wrong thing is removed; a guard with a stated reach is used.

So this catches the INLINE shape, which is the shape `RelatedTab` had and the
shape someone writes when they are not thinking about it. The known
hand-rolled surfaces are documented in the #4464 interaction matrix, which is
where the full picture lives.

## Exceptions are designs, not debt

Some surfaces genuinely cannot be a `List`: a RealityView canvas, a force
-directed graph, a paginated reader. Those live in the allowlist WITH THEIR
REASON, so the file records why rather than merely tolerating.

## Blindness

Exit 2 when the scan population is too small (EPIC #4487). The floor is on
FILES EXAMINED and FOREACH CONSTRUCTS SEEN, not on violations found: a sweep
that matches nothing prints exactly what a clean tree prints, and this one is
expected to sit at zero, so it would spend its whole life indistinguishable
from broken.

Exit codes:
    0   every tappable-row stack is a native container (or an allowed design)
    1   at least one hand-rolled row stack
    2   BLIND -- scan root missing, or the detector matched implausibly little

Usage:
    scripts/check_native_row_containers.py
    scripts/check_native_row_containers.py --list
    scripts/check_native_row_containers.py --root PATH     # tests only
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
ALLOWLIST = Path(__file__).resolve().parent / "native_row_containers_allowlist.json"
RULE_DOC = "#4483 / #4464"

#: Containers that provide selection, arrows and menus natively. A `ForEach`
#: anywhere beneath one of these is fine.
NATIVE = ("List", "Table", "Form", "Picker", "Menu", "Toolbar")

#: Containers that provide nothing. A tappable-row `ForEach` beneath one of
#: these, with no native ancestor, is the defect.
#:
#: **Grids are deliberately absent.** The first draft included `LazyVGrid` and
#: `Grid`, and caught three surfaces: the library's icon mode twice and the
#: workflow card grid. All three are false positives, and instructively so —
#: this rule says "a stack of ROWS should be a List", and a grid of tiles is
#: not a stack of rows. `List` cannot lay out a wrapping tile grid at all, so
#: flagging them would have meant allowlisting three entries whose reason was
#: "the rule does not apply here" — which is a boundary error wearing an
#: allowlist's clothes. The narrower rule is the true one.
BARE = ("ScrollView", "LazyVStack", "LazyHStack", "VStack")

#: Grid containers. A `List` cannot lay out a wrapping tile grid, so this rule
#: simply does not apply to them — they are neither offenders nor exceptions.
GRID = ("LazyVGrid", "LazyHGrid", "Grid")

#: What makes a row "actionable" rather than merely displayed.
TAP_SIGNALS = (
    ".onTapGesture",
    ".simultaneousGesture(TapGesture",
    ".highPriorityGesture(TapGesture",
)

#: Below these, assume the detector broke rather than that the app shrank.
MIN_FILES = 200
MIN_FOREACH = 100


def code_lines(source: str) -> list[str]:
    """Source with `//` comments blanked, so a commented example cannot trip
    the sweep. Not string-literal aware -- a `//` inside a URL literal costs
    us the rest of that line, which is a false NEGATIVE and therefore the safe
    direction for a detector that must not cry wolf."""
    out = []
    for line in source.split("\n"):
        marker = line.find("//")
        out.append(line[:marker] if marker != -1 else line)
    return out


def _closure_body(source: str, open_index: int) -> tuple[str, int]:
    """Text between the brace at `open_index` and its match, plus the end."""
    depth = 0
    for cursor in range(open_index, len(source)):
        char = source[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_index + 1 : cursor], cursor
    return "", len(source)


def _enclosing_chain(source: str, index: int) -> list[str]:
    """Names of every construct enclosing `index`, innermost first.

    Walks OUT by brace matching rather than reading indentation, because
    indentation lies after a line-wrap and this has to survive real formatting.
    """
    chain: list[str] = []
    depth = 0
    cursor = index
    while cursor > 0:
        char = source[cursor]
        if char == "}":
            depth += 1
        elif char == "{":
            if depth == 0:
                head = source[max(0, cursor - 200) : cursor]
                match = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^{]*\))?\s*$", head)
                if match:
                    chain.append(match[-1])
                else:
                    chain.append("?")
            else:
                depth -= 1
        cursor -= 1
    return chain


def scan(views_dir: Path) -> tuple[list[dict], int, int]:
    """Return (offenders, files_scanned, foreach_seen)."""
    offenders: list[dict] = []
    files_scanned = 0
    foreach_seen = 0

    for path in sorted(views_dir.rglob("*.swift")):
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files_scanned += 1
        if "ForEach" not in raw:
            continue

        source = "\n".join(code_lines(raw))

        for match in re.finditer(r"\bForEach\s*\(", source):
            brace = source.find("{", match.end())
            if brace == -1:
                continue
            body, _end = _closure_body(source, brace)
            foreach_seen += 1

            # Half one: is the row actionable at all?
            if not any(signal in body for signal in TAP_SIGNALS):
                continue

            # Half two: which layout container is nearest, walking OUT?
            #
            # Precedence, not membership. Every grid in this app sits inside a
            # `ScrollView`, so asking "is a bare container anywhere above me"
            # answers yes for grids too and flags all three of them. The
            # question is which layout construct is CLOSEST — that is the one
            # deciding the shape.
            chain = _enclosing_chain(source, match.start())
            bare = None
            for name in chain:
                if name in NATIVE:
                    break
                if name in GRID:
                    break
                if name in BARE:
                    bare = name
                    break
            if bare is None:
                # Neither native nor a known bare container -- a ForEach in a
                # helper function, a modifier closure, something else. Not
                # judged: this guard only speaks about row stacks it can see
                # the shape of.
                continue

            offenders.append(
                {
                    "key": str(path.relative_to(views_dir)),
                    "line": source[: match.start()].count("\n") + 1,
                    "container": bare,
                }
            )

    return offenders, files_scanned, foreach_seen


def _load_allowed() -> dict[str, str]:
    if not ALLOWLIST.exists():
        return {}
    return json.loads(ALLOWLIST.read_text())


def _require_population(files_scanned: int, foreach_seen: int) -> None:
    """#4487: the floor sits on the SCAN POPULATION, not on the findings.

    This guard is expected to sit at zero violations forever, so "found
    nothing" is its healthy state AND its broken state. Only the population
    tells them apart.
    """
    if files_scanned >= MIN_FILES and foreach_seen >= MIN_FOREACH:
        return
    print(
        f"check_native_row_containers: BLIND -- examined {files_scanned} file(s) "
        f"and {foreach_seen} ForEach construct(s); expected at least "
        f"{MIN_FILES} and {MIN_FOREACH}. The tree moved or the detector broke, "
        "and a clean result here would be a measurement of nothing.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    views_dir = VIEWS_DIR
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 >= len(argv):
            print("--root needs a path", file=sys.stderr)
            return 2
        views_dir = Path(argv[index + 1])

    if not views_dir.exists():
        print(
            f"check_native_row_containers: BLIND -- scan root missing: {views_dir}",
            file=sys.stderr,
        )
        return 2

    offenders, files_scanned, foreach_seen = scan(views_dir)
    if views_dir == VIEWS_DIR:
        _require_population(files_scanned, foreach_seen)

    allowed = _load_allowed()
    new = [record for record in offenders if record["key"] not in allowed]

    print(f"Native row-container guardrail ({RULE_DOC}):")
    print(
        f"  scanned {files_scanned} file(s), {foreach_seen} ForEach construct(s); "
        f"{len(offenders)} tappable-row stack(s), {len(allowed)} allowed by design."
    )

    if "--list" in argv:
        for record in offenders:
            tag = "allowed" if record["key"] in allowed else "NEW"
            print(f"      [{tag}] {record['key']}:{record['line']} in {record['container']}")
        return 0

    if new:
        print(f"\n  ✗ {len(new)} hand-rolled row stack(s):")
        for record in new:
            print(f"      {record['key']}:{record['line']} — rows inside a {record['container']}")
        print(
            "\nA stack of tappable rows must be `List(selection:)`. A `List` gives\n"
            "arrow keys, shift/⌘ multi-select, the focus ring and a\n"
            "selection-aware context menu for free and correct; a VStack gives\n"
            "none of them, and each one then has to be hand-rolled — which is\n"
            "where every duplicate interaction path in this app came from.\n"
            f"If this surface genuinely cannot be a List, add it to\n"
            f"{ALLOWLIST.name} WITH THE REASON. Rule: {RULE_DOC}."
        )
        return 1

    print("\nPASS every tappable-row stack is a native container.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
