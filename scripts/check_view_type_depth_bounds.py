#!/usr/bin/env python3
"""Guardrail for declared view-type DEPTH BOUNDS in the SwiftUI shell (#4331).

## The crash this protects against

TestFlight v2026.07.29 crashed instantly on iPhone: EXC_BAD_ACCESS, "could not
determine thread index for stack guard region" — a main-thread STACK OVERFLOW
inside `swift_getTypeByMangledNode`, ~120 frames of recursive generic decoding
while the runtime instantiated the library case's fully composed view type.

The identical type fits macOS's 8MB main-thread stack. iOS gets 1MB. That 8x is
the entire reason only the iPhone died, and it is why nothing on the Mac side —
not the build, not the tests, not a simulator run of the Mac scheme — can see
this class of defect.

The fix (0261c80ca) was two `AnyView` erasures placed at chosen points in the
composed type, bounding the mangled-type depth the runtime has to decode.

## Why this file exists

Those erasures look exactly like the redundant `AnyView` wrappers that a style
sweep, a "simplify" pass, or SwiftLint advice would delete on sight. Deleting
either one silently reintroduces a P0 launch crash that:

  - compiles clean,
  - passes every macOS test,
  - passes the iOS Simulator COMPILE gate (it is a runtime metadata cost, not a
    compile error),
  - and is only observable by launching on a physical iPhone.

There is no other mechanism in the tree that forces the erasure and the crash it
prevents to agree. This is that mechanism.

## The rule

An erasure barrier DECLARES itself in source with a marker comment:

    // AnyView is load-bearing (#4331): <why this point, in this chain>
    AnyView(someDeeplyComposedThing)

The sweep is app-wide — any file may declare a barrier, and new ones need no
edit here. For every marker found, an `AnyView(` must appear within
`BARRIER_WINDOW` lines below it. A marker whose erasure was removed is the
regression this catches.

## Knowing when it has gone blind

Deleting the erasure AND its comment would leave nothing to check, and a sweep
that finds nothing to check reads as proof of safety. So:

  - a missing scan root is BLIND (exit 2), not a pass;
  - finding FEWER than `MIN_BARRIERS` declared barriers is a FAILURE, because
    the bounds that were proven necessary on a device cannot quietly become
    unnecessary. Raising the floor when a new bound is added is correct and
    expected; lowering it needs a device launch as evidence, on the issue.

Exit codes:
    0   every declared barrier is intact, and at least MIN_BARRIERS exist
    1   a barrier lost its erasure, or the barrier count fell below the floor
    2   BLIND — the scan root is missing (the tree moved; fix these paths)

Usage:
    scripts/check_view_type_depth_bounds.py
    scripts/check_view_type_depth_bounds.py --list
    scripts/check_view_type_depth_bounds.py --app-dir PATH   # tests only
    scripts/check_view_type_depth_bounds.py --help
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "#4331"

# The bounds proven necessary by the v2026.07.29 device crash: the library-case
# boundary in ContentView+Navigation, and the iPhone-only compact reader stack.
# Raise this when a new bound is added. Lowering it requires device evidence.
MIN_BARRIERS = 2

# How many lines below the marker the erasure may sit. Generous enough for the
# rest of a multi-line explanatory comment, tight enough that an unrelated
# `AnyView(` further down the file cannot satisfy a marker it has nothing to do
# with.
BARRIER_WINDOW = 8

# The self-declaring marker. Deliberately matches the exact phrasing used at the
# two proven sites so an incidental mention of "load-bearing" elsewhere (there
# are ~19 in the app, about isolation, defaults and Equatable) does not become a
# barrier this guard then demands an AnyView for.
_MARKER = re.compile(r"//.*\bAnyView is load-bearing\b", re.IGNORECASE)
_ERASURE = re.compile(r"\bAnyView\s*\(")


def scan(app_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return (intact_barriers, broken_barriers) over every .swift under app_dir.

    A barrier is a marker comment plus a real `AnyView(` within BARRIER_WINDOW
    lines. Broken means the marker survived a sweep that deleted its erasure —
    the exact shape of the regression, since the comment is the thing a
    mechanical edit is least likely to touch.
    """
    intact: list[dict] = []
    broken: list[dict] = []

    for path in sorted(app_dir.rglob("*.swift")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for index, line in enumerate(lines):
            if not _MARKER.search(line):
                continue
            window = lines[index : index + 1 + BARRIER_WINDOW]
            record = {
                "file": _rel(path),
                "line": index + 1,
                "text": line.strip(),
            }
            if any(_ERASURE.search(candidate) for candidate in window):
                intact.append(record)
            else:
                broken.append(record)

    return intact, broken


def _rel(path: Path) -> str:
    """Repo-relative when possible; absolute under a test's tmp dir."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _app_dir_from(argv: list[str]) -> Path:
    """`--app-dir PATH` overrides the scan root.

    This exists so the self-test can synthesise its OWN violation in a tmp tree
    rather than mutating (or asserting against) the real one. A guardrail whose
    only positive fixture is the committed source proves nothing the moment that
    source legitimately changes.
    """
    if "--app-dir" in argv:
        index = argv.index("--app-dir")
        if index + 1 >= len(argv):
            print("--app-dir needs a path", file=sys.stderr)
            raise SystemExit(2)
        return Path(argv[index + 1])
    return APP_DIR


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    app_dir = _app_dir_from(argv)
    _require_scan_roots_4382(app_dir)
    intact, broken = scan(app_dir)

    if "--list" in argv:
        print(f"Declared view-type depth bounds ({len(intact) + len(broken)}):\n")
        for record in intact + broken:
            tag = "intact" if record in intact else "BROKEN"
            print(f"  [{tag}] {record['file']}:{record['line']}")
        return 0

    print(f"View-type depth-bound guardrail: swept {_rel(app_dir)}")
    print(f"  {len(intact)} intact barrier(s); floor is {MIN_BARRIERS}.")

    failed = False

    if broken:
        failed = True
        print(
            f"\n  {len(broken)} declared barrier(s) lost the AnyView erasure they "
            "describe:"
        )
        for record in broken:
            print(f"      {record['file']}:{record['line']}  {record['text']}")

    if len(intact) < MIN_BARRIERS:
        failed = True
        print(
            f"\n  Only {len(intact)} intact barrier(s); {MIN_BARRIERS} were proven "
            "necessary by a device crash."
        )

    if failed:
        print(
            "\nThese AnyView erasures bound the depth of the mangled type the Swift\n"
            "runtime decodes while instantiating the shell's composed view. Without\n"
            "them the recursion overflows the iOS main thread's 1MB stack and the app\n"
            "dies at launch on a physical iPhone — while compiling clean, passing the\n"
            "macOS suite, and passing the iOS Simulator compile gate.\n"
            f"Restore the erasure, or prove on a device that it is no longer needed\n"
            f"and say so on {RULE_DOC} before lowering MIN_BARRIERS."
        )
        return 1

    print("\nPASS every declared view-type depth bound is intact.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    missing = [str(root) for root in roots if not root.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    raise SystemExit(main())
