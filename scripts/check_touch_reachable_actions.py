#!/usr/bin/env python3
"""A double-click action needs a path that exists on a touch screen (#4505).

iPad and iPhone have no double-click. So a view whose only route to an action is
`TapGesture(count: 2)` — or `.onTapGesture(count: 2)` — offers that action to
Mac users and to nobody else. The code looks complete, the Mac behaves, and the
action is simply absent on half the platforms the app ships to.

Three sites existed when this was written and they were not equivalent, which is
the argument for checking rather than assuming:

  * `ArtifactListView` paired its double-click with a "Open in Window" context
    menu item — reachable by long-press, fine.
  * `openEntity` and `openClaim` each had EXACTLY ONE caller, the double-click.
    Opening an entity, and jumping from a claim to its source page, were
    unreachable on iPad entirely — the second on the surface whose whole
    argument is that a claim must be traceable back to the page (#4393).

The rule is therefore not "no double-click". Double-click is a good Mac
accelerator and removing it would make the Mac worse. The rule is that the
action must ALSO be reachable some other way: a context menu item, or a button.

This is static and deliberately shallow — it asks whether the file that mounts a
double-click also offers a non-gesture affordance. It cannot prove the menu item
invokes the SAME action; that is what the paired unit tests are for. A shallow
check that runs on every file beats a deep one that runs on the three sites
somebody remembered.

Run: python3 scripts/check_touch_reachable_actions.py [--self-test]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _check_floor import require_scan_floor  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "fichero" / "fichero"

# Both spellings of "double click" that SwiftUI offers.
_DOUBLE = re.compile(r"TapGesture\(count:\s*2\)|\.onTapGesture\(count:\s*2\)")
# A non-gesture affordance: long-press menu, or a real button.
_FALLBACK = re.compile(r"\.contextMenu\b|\bButton\(|\bButton\s*\{")

# Files where a double-click is genuinely the only sensible interaction AND the
# surface does not ship to touch. Keyed to why. Empty is the goal.
KNOWN: dict[str, str] = {}


def swift_sources(root: Path) -> list[Path]:
    """App Swift files, excluding build products.

    `.build` and DerivedData exist only in a worktree somebody has compiled, so
    walking them makes the population depend on whether a build happened — and a
    check whose answer depends on that is not a check (#4487).
    """
    return [
        p
        for p in sorted(root.rglob("*.swift"))
        if ".build" not in p.parts and "DerivedData" not in p.parts
    ]


def strip_mac_only(text: str) -> str:
    """Remove `#if os(macOS)` / `#if canImport(AppKit)` regions.

    A gesture that does not COMPILE on iPad cannot be an iPad reachability
    problem, so those regions are out of scope by definition rather than by
    indulgence. This was found by measurement, not foresight: the first version
    of this rule flagged `SidebarView+ViewComponents`, whose double-click is
    Mac-only and whose own comment says the row context menu carries the same
    action — the menu simply lives in a sibling file. Both reasons to ignore it,
    and the rule knew neither.

    `#else` matters: the else-branch of a macOS test is exactly the touch code,
    so it is kept.
    """
    out: list[str] = []
    depth_mac = 0
    depth_any = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#if"):
            depth_any += 1
            if depth_mac == 0 and ("os(macOS)" in stripped or "canImport(AppKit)" in stripped):
                depth_mac = depth_any
                continue
        elif stripped.startswith("#endif"):
            if depth_mac == depth_any:
                depth_mac = 0
                depth_any -= 1
                continue
            depth_any -= 1
        elif stripped.startswith("#else") and depth_mac == depth_any and depth_mac:
            # Leaving the macOS branch: everything after this IS touch code.
            depth_mac = 0
            continue
        if depth_mac:
            continue
        out.append(line)
    return "\n".join(out)


def strip_comments(text: str) -> str:
    """Drop `//` line comments.

    Also found by measurement rather than foresight. `SidebarItemRow+Label` was
    flagged for a `TapGesture(count: 2)` that appears only inside a comment
    explaining why the file deliberately does NOT use one (#612) — the rule read
    a warning against the pattern as an instance of it. A check that fires on
    prose about itself is the same failure as one that fires on its own
    explanation, which this repo has now hit twice.
    """
    return "\n".join(line.split("//")[0] for line in text.split("\n"))


def is_unreachable_on_touch(text: str) -> bool:
    """True when this file mounts a double-click reachable on touch platforms
    and offers no other route to it."""
    touch = strip_comments(strip_mac_only(text))
    return bool(_DOUBLE.search(touch)) and not _FALLBACK.search(touch)


def main() -> int:
    files = swift_sources(APP)
    # 912 app Swift files at commit time; floor at half, per #4487's convention.
    require_scan_floor(len(files), 456, "app Swift files")

    with_double: list[str] = []
    unreachable: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not _DOUBLE.search(strip_comments(strip_mac_only(text))):
            continue
        rel = str(path.relative_to(REPO))
        with_double.append(rel)
        if is_unreachable_on_touch(text):
            unreachable.append(rel)

    new = [p for p in unreachable if p not in KNOWN]
    stale = [p for p in KNOWN if p not in unreachable]

    print(
        f"Touch-reachable actions: {len(with_double)} file(s) mount a double-click, "
        f"of {len(files)} scanned."
    )
    if not new and not stale:
        print("  ✓ every double-click surface also offers a menu or a button.")
        return 0

    for path in new:
        print(f"  ✗ {path} — double-click is the only route to its action.")
        print("     iPad has no double-click, so that action does not exist there.")
        print("     Add a context-menu item or a button; keep the double-click.")
    for path in stale:
        print(f"  ✗ {path} is in KNOWN ({KNOWN[path]}) but now has a fallback — remove it.")
    return 1


def self_test() -> int:
    """Every rule fires. A check nobody has watched fail is a check nobody tested."""
    # 1. double-click with no other route → caught
    assert is_unreachable_on_touch('.simultaneousGesture(TapGesture(count: 2).onEnded { open() })')
    # 2. the other spelling is caught too — the three real sites used BOTH,
    #    and a rule that knew only one would have passed on two of them
    assert is_unreachable_on_touch('.onTapGesture(count: 2) { open() }')
    # 3. paired with a context menu → fine
    assert not is_unreachable_on_touch(
        '.onTapGesture(count: 2) { open() }\n.contextMenu { Text("x") }'
    )
    # 4. paired with a button → fine
    assert not is_unreachable_on_touch('TapGesture(count: 2)\nButton("Open") { open() }')
    # 5. no double-click at all → no opinion
    assert not is_unreachable_on_touch('.onTapGesture { select() }')
    # 5b. a Mac-only double-click cannot be a touch problem — it does not
    #     compile there. Found by measurement: the first version flagged
    #     SidebarView+ViewComponents for exactly this.
    assert not is_unreachable_on_touch(
        '#if os(macOS)\n.onTapGesture(count: 2) { open() }\n#endif'
    )
    # 5c. but the #else branch IS touch code and stays in scope
    assert is_unreachable_on_touch(
        '#if os(macOS)\nlet x = 1\n#else\n.onTapGesture(count: 2) { open() }\n#endif'
    )
    # 5d. a comment WARNING against double-click is not an instance of one
    assert not is_unreachable_on_touch('// never use TapGesture(count: 2) here')
    # 6. build products excluded, so the result cannot depend on a compile
    assert not [p for p in swift_sources(APP) if ".build" in p.parts]

    print("check_touch_reachable_actions self-test: OK — all nine rules fire.")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
