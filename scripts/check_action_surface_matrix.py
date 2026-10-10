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

from _check_floor import require_scan_floor
from dataclasses import dataclass
from pathlib import Path

from matrix_guardrail_common import ROOT, load_known_gaps
from _scan_files import scan_rglob

APP_SOURCE = ROOT / "fichero" / "fichero" / "FicheroApp.swift"
KNOWN_GAPS = load_known_gaps(Path(__file__).with_name("check_action_surface_matrix_known_gaps.json"))

# Menu Commands live in App/Menus (moved out of the Views/Shell catch-all).
MENUS_DIR = ROOT / "fichero" / "fichero" / "App" / "Menus"
MENU_FILES = {
    MENUS_DIR / "FileMenuCommands.swift",
    MENUS_DIR / "ViewMenuCommands.swift",
    MENUS_DIR / "ViewMenuLayoutSections.swift",
    MENUS_DIR / "ViewMenuSortAndModeSections.swift",
    MENUS_DIR / "ViewMenuPaneSections.swift",
    MENUS_DIR / "ImagePreviewMenuCommands.swift",
    MENUS_DIR / "AddItemMenu.swift",
    # `CommandMenu("Read")`/`CommandMenu("Knowledge")`, inserted at
    # FicheroApp.swift:524 — genuinely a menu file, just never added here
    # (found 2026-09-27: it holds six of the "New …" creation buttons this
    # matrix already names, and every one of them was reporting a false
    # "missing menu").
    MENUS_DIR / "ReadKnowledgeMenuCommands.swift",
}

# The `Focused*Button` wrapper structs (menu_refs' targets) used to live in one
# file; a later file-length split moved them into this subfolder, one topic
# per file, and left `WRAPPER_SOURCE` pointing at a path that no longer exists
# (found 2026-09-27 alongside the MENU_FILES gap above — the same class of
# defect, a split silently narrowing what a guard reads). Scanned as a whole
# directory rather than re-pinning one filename, so the NEXT split inside it
# does not repeat this.
WRAPPER_DIR = MENUS_DIR / "FocusedCommands"

# Toolbar/context evidence lives across Views/ AND App/Menus/ (AddItemMenu carries
# the only toolbar evidence for some Link/Copy/Add-Files actions after the reorg).
_EVIDENCE_ROOTS = [
    scan_rglob((ROOT / "fichero" / "fichero" / "Views"), "*.swift"),
    scan_rglob(MENUS_DIR, "*.swift"),
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
WRAPPER_TEXT = "\n".join(
    _read_text(path) for path in sorted(WRAPPER_DIR.glob("*.swift"))
) if WRAPPER_DIR.is_dir() else ""
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
        action="Set Up New Project…",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Set Up New Project…\"",),
        keyboard_patterns=("Button(\"Set Up New Project…\"",),
    ),
    ActionSpec(
        action="Open…",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Open…\"",),
        keyboard_patterns=("Button(\"Open…\"",),
    ),
    ActionSpec(
        action="Close Project",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Close Project\"",),
        keyboard_patterns=("Button(\"Close Project\"",),
    ),
    ActionSpec(
        action="New Window",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"New Window\"",),
        keyboard_patterns=("Button(\"New Window\"",),
    ),
    ActionSpec(
        action="Save Project As…",
        expected=("menu", "keyboard"),
        menu_patterns=("Button(\"Save Project As…\"",),
        keyboard_patterns=("Button(\"Save Project As…\"",),
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
    # "New Search" retired with the search mode (#4106/#4086): searching is
    # the toolbar field, never a created object — no surfaces expected.
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
    # Renamed from "Find in Artifact" (found 2026-09-27: the action was never
    # missing, its own name had moved on — `ShowFindBarButton` in
    # ViewMenuPaneSections.swift, already `⌘⌥F`).
    ActionSpec(
        action="Find in Page",
        expected=("menu", "keyboard"),
        menu_patterns=("Find in Page",),
        keyboard_patterns=("Find in Page",),
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
            # A `menu_refs` button is placed EITHER directly in FicheroApp.swift
            # (Rename/Delete's own wiring) OR by being rendered from inside one
            # of the named menu files (New Folder/New Chat/etc., via
            # FileMenuCommands()/ReadKnowledgeMenuCommands() — both real
            # CommandGroup/CommandMenu content, just one file removed from
            # FicheroApp.swift's own text). Checking APP_TEXT alone reported
            # six real menu items as missing (found 2026-09-27).
            menu = all(ref in APP_TEXT or ref in MENU_TEXT for ref in spec.menu_refs)
            if menu:
                evidence.append("menu:FicheroApp.swift+App/Menus")
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
    # #4487 scan floors. The 34 actions are a COMMITTED matrix, so their
    # count only proves the constant exists; the discoverable half is the
    # Swift evidence scan, and a dead one is masked by the known-gaps
    # baseline (every action reads "missing menu" and every miss is known).
    # Floor the evidence population too: 588 files on 2026-08-02.
    require_scan_floor(len(rows), 17, "registered actions (34 on 2026-08-02)")
    require_scan_floor(
        len(_EVIDENCE_FILES), 294, "Swift evidence files (588 on 2026-08-02)"
    )
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
