#!/usr/bin/env python3
"""Sidebar item wiring guardrail — best-effort static check.

Rule (#1946): sidebar item factories/builders should map to a destination case
that the main content router handles. This detector scans:
  - `Models/SidebarItem*.swift` and `Models/SidebarItemBuilder.swift` for
    `itemType: .foo` factories/builders.
  - `Models/SidebarViewTypes.swift` for `AppViewMode` cases.
  - `Views/Shell/ContentView/ContentView+Navigation.swift` for the routed destination switch.

Limits: this is not a full Swift compiler or runtime navigation proof. It checks
that each sidebar leaf item type has a corresponding `AppViewMode` destination
case and that the destination case appears in the content router. Structural
sidebar items (`folder`, `libraryHeader`) are intentionally ignored. See
agents/ROADMAP.md for the guardrail roadmap.

Usage:
    python3 scripts/check_sidebar_items.py
    python3 scripts/check_sidebar_items.py --list
    python3 scripts/check_sidebar_items.py -h
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
RULE_DOC = "agents/ROADMAP.md"

SIDEBAR_SOURCES = [
    SWIFT_ROOT / "Models" / "SidebarItem.swift",
    SWIFT_ROOT / "Models" / "SidebarItem+MoreFactories.swift",
    SWIFT_ROOT / "Models" / "SidebarItemBuilder.swift",
]
VIEW_MODE_FILE = SWIFT_ROOT / "Models" / "SidebarViewTypes.swift"
ROUTER_FILE = SWIFT_ROOT / "Views" / "Shell" / "ContentView" / "ContentView+Navigation.swift"

STRUCTURAL_ITEM_TYPES = {"folder", "libraryHeader"}
ITEM_TO_VIEW_MODE: dict[str, str] = {
    "document": "library",
    "savedSearch": "search",
    "conversation": "chat",
    "workflow": "workflow",
    "chain": "chain",
    "comparison": "comparison",
    "schedule": "schedule",
    "trigger": "trigger",
    "batch": "batch",
    "activityRun": "activity",
}

# Current sidebar wiring backlog. Drop entries as destinations are wired.
KNOWN_VIOLATIONS: dict[str, str] = {}


def read(path: Path) -> str:
    return path.read_text(errors="ignore") if path.exists() else ""


def built_item_types() -> set[str]:
    text = "\n".join(read(path) for path in SIDEBAR_SOURCES)
    return {
        match.group(1)
        for match in re.finditer(r"\bitemType:\s*\.([A-Za-z_][A-Za-z0-9_]*)\b", text)
        if match.group(1) not in STRUCTURAL_ITEM_TYPES
    }


def app_view_modes() -> set[str]:
    text = read(VIEW_MODE_FILE)
    return set(re.findall(r"^\s*case\s+([A-Za-z_][A-Za-z0-9_]*)\b", text, re.MULTILINE))


def routed_view_modes() -> set[str]:
    text = read(ROUTER_FILE)
    return set(re.findall(r"^\s*case\s+\.([A-Za-z_][A-Za-z0-9_]*)\b", text, re.MULTILINE))


def scan() -> dict[str, list[str]]:
    modes = app_view_modes()
    routes = routed_view_modes()
    found: dict[str, list[str]] = {}

    for item_type in sorted(built_item_types()):
        expected = ITEM_TO_VIEW_MODE.get(item_type)
        reasons: list[str] = []
        if expected is None:
            reasons.append("no static itemType-to-AppViewMode mapping in detector")
        elif expected not in modes:
            reasons.append(f"expected AppViewMode.{expected}, but that case is missing")
        elif expected not in routes:
            reasons.append(f"AppViewMode.{expected} exists, but ContentView router has no case")
        if reasons:
            found[item_type] = reasons

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Sidebar item wiring offenders ({len(found)} item type(s)):\n")
        for item_type, reasons in sorted(found.items()):
            tag = "known" if item_type in known else "NEW"
            print(f"  [{tag}] {item_type}")
            for reason in reasons:
                print(f"          - {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print("Sidebar item wiring guardrail: scanned SidebarItem factories/builders and ContentView router")
    print(f"  {len(found)} unwired item type(s); {len(known)} known backlog entries.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for item_type in stale:
            print(f"      {item_type}")

    if new:
        print(f"\n  ✗ {len(new)} sidebar item type(s) without a wired destination:")
        for item_type in new:
            for reason in found[item_type]:
                print(f"      {item_type}  ←  {reason}")
        print(
            "\nFix: add/route the matching AppViewMode destination, or extend this detector "
            f"with the intentional mapping. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No sidebar item wiring offenders beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
