#!/usr/bin/env python3
"""Completeness-matrix guardrail for Mac action surfaces (#1925).

This is a conservative, ratcheting scan for named user-facing actions across
the four Mac affordances we care about:

* menu / CommandMenu wiring
* contextual menus
* toolbar affordances
* keyboard shortcuts

The scan intentionally starts from the keyboard-shortcut spine plus the main
creation / destructive actions that already have a canonical menu wiring path.
It only flags gaps we can detect with confidence. Today's known gaps are seeded
in `check_action_surface_matrix_known_gaps.json`, so the script exits 0 now and
only fails when a new action loses one of its expected surfaces.

Usage:
    scripts/check_action_surface_matrix.py
    scripts/check_action_surface_matrix.py --list
    scripts/check_action_surface_matrix.py --help
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from matrix_guardrail_common import ROOT, load_known_gaps

APP_SOURCE = ROOT / "fichero" / "fichero" / "FicheroApp.swift"
WRAPPER_SOURCE = ROOT / "fichero" / "fichero" / "App" / "Menus" / "FocusedCommandButtons.swift"
KNOWN_GAPS = load_known_gaps(Path(__file__).with_name("check_action_surface_matrix_known_gaps.json"))

# Menu Commands live in App/Menus (moved out of the Views/Shell catch-all).
MENUS_DIR = ROOT / "fichero" / "fichero" / "App" / "Menus"
MENU_FILES = {
    MENUS_DIR / "FileMenuCommands.swift",
    MENUS_DIR / "ViewMenuCommands.swift",
    MENUS_DIR / "ViewMenuLayoutSections.swift",
    MENUS_DIR / "ViewMenuPaneSections.swift",
    MENUS_DIR / "ImagePreviewMenuCommands.swift",
    MENUS_DIR / "AddItemMenu.swift",
}

# Toolbar/context evidence lives across Views/ AND App/Menus/ (AddItemMenu carries
# the only toolbar evidence for some Link/Copy/Add-Files actions after the reorg).
_EVIDENCE_ROOTS = [
    (ROOT / "fichero" / "fichero" / "Views").rglob("*.swift"),
    MENUS_DIR.rglob("*.swift"),
]
_EVIDENCE_FILES = {path for root in _EVIDENCE_ROOTS for path in root}

CONTEXT_FILES = {
    path
    for path in _EVIDENCE_FILES
    if "ContextMenu" in path.name
    or ".contextMenu" in path.read_text(encoding="utf-8", errors="ignore")
}

TOOLBAR_FILES = {
    path
    for path in _EVIDENCE_FILES
    if "Toolbar" in path.name
    or "Toolbar" in path.read_text(encoding="utf-8", errors="ignore")
    or "ToolbarItem" in path.read_text(encoding="utf-8", errors="ignore")
    or ".toolbar" in path.read_text(encoding="utf-8", errors="ignore")
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


APP_TEXT = _read_text(APP_SOURCE)
WRAPPER_TEXT = _read_text(WRAPPER_SOURCE)
MENU_TEXT = "\n".join(_read_text(path) for path in sorted(MENU_FILES))
CONTEXT_TEXT = "\n".join(_read_text(path) for path in sorted(CONTEXT_FILES))
TOOLBAR_TEXT = "\n".join(_read_text(path) for path in sorted(TOOLBAR_FILES))


@dataclass(frozen=True)
class Row:
    action: str
    menu: bool
    context_menu: bool
    toolbar: bool
    keyboard: bool
    expected: tuple[str, ...]
    evidence: tuple[str, ...]

    @property
    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        for surface in self.expected:
            if surface == "menu" and not self.menu:
                missing.append(surface)
            elif surface == "context" and not self.context_menu:
                missing.append(surface)
            elif surface == "toolbar" and not self.toolbar:
                missing.append(surface)
            elif surface == "keyboard" and not self.keyboard:
                missing.append(surface)
        return tuple(missing)

    @property
    def gap(self) -> bool:
        return bool(self.missing)


@dataclass(frozen=True)
class ActionSpec:
    action: str
    expected: tuple[str, ...]
    menu_refs: tuple[str, ...] = ()
    menu_patterns: tuple[str, ...] = ()
    context_patterns: tuple[str, ...] = ()
    toolbar_patterns: tuple[str, ...] = ()
    keyboard_patterns: tuple[str, ...] = ()


ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        action="New Library...",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"New Library...\"",),
        keyboard_patterns=("Button(\"New Library...\"",),
    ),
    ActionSpec(
        action="Open...",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Open...\"",),
        keyboard_patterns=("Button(\"Open...\"",),
    ),
    ActionSpec(
        action="Close Database",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Close Database\"",),
        keyboard_patterns=("Button(\"Close Database\"",),
    ),
    ActionSpec(
        action="New Window",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"New Window\"",),
        keyboard_patterns=("Button(\"New Window\"",),
    ),
    ActionSpec(
        action="Save Database As...",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Save Database As...\"",),
        keyboard_patterns=("Button(\"Save Database As...\"",),
    ),
    ActionSpec(
        action="New Folder",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedNewFolderButton",),
        toolbar_patterns=("New Folder",),
        keyboard_patterns=("FocusedNewFolderButton",),
    ),
    ActionSpec(
        action="Link Files...",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedImportFilesButton",),
        toolbar_patterns=("Link Files...",),
        keyboard_patterns=("Link Files...",),
    ),
    ActionSpec(
        action="Copy Files...",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedImportFilesButton",),
        toolbar_patterns=("Copy Files...",),
        keyboard_patterns=("Copy Files...",),
    ),
    ActionSpec(
        action="Add Files...",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedImportFilesButton",),
        toolbar_patterns=("Add Files...",),
        keyboard_patterns=("Add Files...",),
    ),
    ActionSpec(
        action="Rename",
        expected=("menu", "context", "keyboard"),
        menu_refs=("FocusedRenameButton",),
        context_patterns=("Rename",),
        keyboard_patterns=("FocusedRenameButton",),
    ),
    ActionSpec(
        action="Delete",
        expected=("menu", "context", "keyboard"),
        menu_refs=("FocusedDeleteButton",),
        context_patterns=("Delete",),
        keyboard_patterns=("FocusedDeleteButton",),
    ),
    ActionSpec(
        action="New Search",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedNewSearchButton",),
        toolbar_patterns=("New Search",),
        keyboard_patterns=("FocusedNewSearchButton",),
    ),
    ActionSpec(
        action="New Chat",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedNewChatButton",),
        toolbar_patterns=("New Chat",),
        keyboard_patterns=("FocusedNewChatButton",),
    ),
    ActionSpec(
        action="New Workflow",
        expected=("menu", "toolbar", "keyboard"),
        menu_refs=("FocusedNewWorkflowButton",),
        toolbar_patterns=("New Workflow",),
        keyboard_patterns=("FocusedNewWorkflowButton",),
    ),
    ActionSpec(
        action="New Chain",
        expected=("menu", "toolbar"),
        menu_refs=("FocusedNewChainButton",),
        toolbar_patterns=("New Chain",),
    ),
    ActionSpec(
        action="New Comparison",
        expected=("menu", "toolbar"),
        menu_refs=("FocusedNewComparisonButton",),
        toolbar_patterns=("New Comparison",),
    ),
    ActionSpec(
        action="New Schedule",
        expected=("menu", "toolbar"),
        menu_refs=("FocusedNewScheduleButton",),
        toolbar_patterns=("New Schedule",),
    ),
    ActionSpec(
        action="New Trigger",
        expected=("menu", "toolbar"),
        menu_refs=("FocusedNewTriggerButton",),
        toolbar_patterns=("New Trigger",),
    ),
    ActionSpec(
        action="Run Workflow on Selection...",
        expected=("menu", "context", "keyboard"),
        menu_refs=("FocusedRunWorkflowOnSelectionButton",),
        menu_patterns=("Run Workflow on Selection...",),
        context_patterns=("Run Workflow",),
        keyboard_patterns=("FocusedRunWorkflowOnSelectionButton",),
    ),
    ActionSpec(
        action="Show Inspector",
        expected=("menu", "keyboard"),
        menu_patterns=("Show Inspector",),
        keyboard_patterns=("Show Inspector",),
    ),
    ActionSpec(
        action="Go Up",
        expected=("menu", "keyboard"),
        menu_patterns=("Go Up",),
        keyboard_patterns=("Go Up",),
    ),
    ActionSpec(
        action="Show Ruler",
        expected=("menu", "keyboard"),
        menu_patterns=("Show Ruler",),
        keyboard_patterns=("Show Ruler",),
    ),
    ActionSpec(
        action="Find in Artifact",
        expected=("menu", "keyboard"),
        menu_patterns=("Find in Artifact",),
        keyboard_patterns=("Find in Artifact",),
    ),
    ActionSpec(
        action="Actual Size",
        expected=("menu", "keyboard"),
        menu_patterns=("Actual Size",),
        keyboard_patterns=("Actual Size",),
    ),
    ActionSpec(
        action="Zoom to Fit",
        expected=("menu", "keyboard"),
        menu_patterns=("Zoom to Fit",),
        keyboard_patterns=("Zoom to Fit",),
    ),
    ActionSpec(
        action="Zoom In",
        expected=("menu", "keyboard"),
        menu_patterns=("Zoom In",),
        keyboard_patterns=("Zoom In",),
    ),
    ActionSpec(
        action="Zoom Out",
        expected=("menu", "keyboard"),
        menu_patterns=("Zoom Out",),
        keyboard_patterns=("Zoom Out",),
    ),
    ActionSpec(
        action="Magnifier Panel",
        expected=("menu", "keyboard"),
        menu_patterns=("Magnifier Panel",),
        keyboard_patterns=("Magnifier Panel",),
    ),
    ActionSpec(
        action="Lock Magnifier",
        expected=("menu", "keyboard"),
        menu_patterns=("Lock Magnifier",),
        keyboard_patterns=("Lock Magnifier",),
    ),
    ActionSpec(
        action="Magnifier Zoom In",
        expected=("menu", "keyboard"),
        menu_patterns=("Magnifier Zoom In",),
        keyboard_patterns=("Magnifier Zoom In",),
    ),
    ActionSpec(
        action="Magnifier Zoom Out",
        expected=("menu", "keyboard"),
        menu_patterns=("Magnifier Zoom Out",),
        keyboard_patterns=("Magnifier Zoom Out",),
    ),
    ActionSpec(
        action="Loupe",
        expected=("menu", "keyboard"),
        menu_patterns=("Loupe",),
        keyboard_patterns=("Loupe",),
    ),
    ActionSpec(
        action="Lock Loupe",
        expected=("menu", "keyboard"),
        menu_patterns=("Lock Loupe",),
        keyboard_patterns=("Lock Loupe",),
    ),
    ActionSpec(
        action="Loupe Zoom In",
        expected=("menu", "keyboard"),
        menu_patterns=("Loupe Zoom In",),
        keyboard_patterns=("Loupe Zoom In",),
    ),
    ActionSpec(
        action="Loupe Zoom Out",
        expected=("menu", "keyboard"),
        menu_patterns=("Loupe Zoom Out",),
        keyboard_patterns=("Loupe Zoom Out",),
    ),
)


def _match(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _evidence(label: str, text: str, patterns: tuple[str, ...], source_name: str) -> tuple[str, ...]:
    if not patterns or not text:
        return ()
    if _match(text, patterns):
        return (f"{label}:{source_name}",)
    return ()


def scan() -> list[Row]:
    rows: list[Row] = []
    for spec in ACTION_SPECS:
        menu = False
        evidence: list[str] = []

        if spec.menu_refs:
            menu = all(ref in APP_TEXT for ref in spec.menu_refs)
            if menu:
                evidence.append("menu:FicheroApp.swift")
        elif spec.menu_patterns:
            menu = _match(MENU_TEXT, spec.menu_patterns)
            if menu:
                evidence.append("menu:App/Menus")

        context = _match(CONTEXT_TEXT, spec.context_patterns)
        if context:
            evidence.append("context:Views/**/ContextMenu")

        toolbar = _match(TOOLBAR_TEXT, spec.toolbar_patterns)
        if toolbar:
            evidence.append("toolbar:Views/**/Toolbar*")

        keyboard_sources = (APP_TEXT, WRAPPER_TEXT, MENU_TEXT)
        keyboard = any(
            _match(text, spec.keyboard_patterns) and ".keyboardShortcut" in text
            for text in keyboard_sources
        )
        if keyboard:
            evidence.append("keyboard:.keyboardShortcut")

        rows.append(
            Row(
                action=spec.action,
                menu=menu,
                context_menu=context,
                toolbar=toolbar,
                keyboard=keyboard,
                expected=spec.expected,
                evidence=tuple(evidence),
            )
        )
    return rows


def _print_matrix(rows: list[Row]) -> None:
    for row in rows:
        status = "known" if row.action in KNOWN_GAPS else "NEW" if row.gap else "ok"
        missing = ", ".join(row.missing) if row.missing else "-"
        evidence = ", ".join(row.evidence) if row.evidence else "-"
        print(
            f"  [{status}] {row.action} | menu={'Y' if row.menu else 'N'} | "
            f"context={'Y' if row.context_menu else 'N'} | toolbar={'Y' if row.toolbar else 'N'} | "
            f"keyboard={'Y' if row.keyboard else 'N'} | missing={missing} | evidence={evidence}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    found = {row.action: row for row in rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"Action surface matrix ({len(rows)} actions):\n")
        _print_matrix(rows)
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))
    menu_missing = sum(1 for row in rows if "menu" in row.missing)
    context_missing = sum(1 for row in rows if "context" in row.missing)
    toolbar_missing = sum(1 for row in rows if "toolbar" in row.missing)
    keyboard_missing = sum(1 for row in rows if "keyboard" in row.missing)
    unclassified = sorted(row.action for row in rows if not row.evidence)

    print("Action surface matrix guardrail:")
    print(f"  scanned {len(rows)} action(s)")
    print(f"  menu gaps: {menu_missing}")
    print(f"  context gaps: {context_missing}")
    print(f"  toolbar gaps: {toolbar_missing}")
    print(f"  keyboard gaps: {keyboard_missing}")
    print(f"  current gaps: {len(found)}; known baseline: {len(known)}")

    if unclassified:
        print(f"  unclassified action(s): {len(unclassified)}")
        for action in unclassified:
            print(f"      {action}")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for action in stale:
            print(f"      {action}")

    if new:
        print(f"\n  {len(new)} new action surface gap(s):")
        for action in new:
            row = found[action]
            print(
                f"      {action}  <-  missing {', '.join(row.missing)}"
            )
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ No action surface gaps beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
