#!/usr/bin/env python3
"""Dead Swift file guardrail — flag files whose primary types are unreferenced.

Rule (#1945): a Swift source file under `fichero/fichero` is a candidate dead file
when its primary struct/class/enum type names are never referenced by any other
Swift file.

This is conservative. It skips app entry points, preview types, files without a
clear primary type, and names referenced anywhere else (including `#Preview`).
String-based/reflection lookups are not generally provable, so add intentional
exceptions to `KNOWN_VIOLATIONS` only with an issue note. See agents/ROADMAP.md for
the guardrail roadmap.

Usage:
    python3 scripts/check_dead_files.py
    python3 scripts/check_dead_files.py --list
    python3 scripts/check_dead_files.py -h
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
RULE_DOC = "agents/ROADMAP.md"

TYPE_DECL = re.compile(
    r"^\s*(?:@[A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|private|fileprivate|internal|open|final)\s+)*"
    r"(?:struct|class|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.MULTILINE,
)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"(?<!:)//.*")
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
#: A file can be reached through an EXTENSION on somebody else's type, and then it declares no
#: type anybody names — only methods. That is the single blind spot behind 24 of this guard's 50
#: allowlist entries, every one of them reading "extension file; scanner misses same-file
#: extension wiring". Two live files were still being reported on 2026-09-27:
#: ReaderFolderProxy.swift (folderProxy/folderProxyContent, called from ReadingPaneView+Tabs)
#: and ContentView+SelectionAndDetailEvents.swift (handleBrowserSelectionChange and
#: handleDetailDocumentChange, called from ContentView+RootLayout).
EXTENSION_BLOCK = re.compile(r"^\s*extension\s+[A-Za-z_]", re.M)
FUNC_DECL = re.compile(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*[(<]")
#: Protocol requirements every conforming file declares, so a match on one says nothing about
#: whether THIS file is reached. `body` alone would make every SwiftUI view file look alive.
PROTOCOL_REQUIREMENTS = frozenset({
    "body", "makeBody", "makeNSView", "updateNSView", "makeUIView", "updateUIView",
    "makeCoordinator", "hash", "encode", "validate", "update", "reset", "callAsFunction",
})

# Current candidate-dead backlog. Drop entries as files are removed or wired.
KNOWN_VIOLATIONS: dict[str, str] = {
    # #5110 — BUILT AND UNREACHABLE, which is not the same as dead. Each is one SwiftUI view,
    # no extension on another type, and no presentation site anywhere: no `.sheet(item:)`, no
    # menu command, no context action. Entity merge and split are real ontology operations and
    # the engine side exists, so deleting them throws away built work while wiring them is a
    # product decision about where the door goes. Verified 2026-09-27 by classifying every
    # reference as code or prose first — each type name appears exactly once, at its own
    # declaration. Do not let these entries outlive the ruling on #5110.
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift": (
        "#5110 — built, compiles, no door: merging two knowledge-graph entities"
    ),
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift": (
        "#5110 — built, compiles, no door: splitting one entity into two"
    ),
    "Views/Onboarding/FirstRunWindow+Library.swift": (
        "#5110 — built, compiles, no door: the first-run library setup actions row"
    ),
    "Views/Shell/ContentView/Layout/ContentView+WindowEnvironment.swift": (
        "#4902 — false positive, NOT dead: WindowEnvironmentModifier IS used, but only "
        "indirectly — three boundaries (ContentView+Navigation.swift:154, PaneSpec.swift:313, "
        "ContentView+RootLayout.swift:57) call `.modifier(windowEnvironment)`, the lowercase "
        "COMPUTED PROPERTY declared in this same file, never spelling out the type name "
        "`WindowEnvironmentModifier` again outside its own declaration. The scanner's "
        "type-name-reference heuristic can't see through that indirection."
    ),
    "Views/Preview/EntrySourcePreview.swift": "#4235-class — extension-heavy view file; LadderLevel is the private containment-ladder rung enum used only by this view's own step logic (2026-08-23)",
    "Views/Workflow/Library/WorkflowChainListView.swift": "2026-08-10 — candidate dead file: orphaned when the legacy WorkflowLibraryView list was removed (workflow clicks route straight to the node editor). Daniel is leaning 'chains fold into workflows'; delete this (and its Parts/) or rewire once he rules. Do not let this entry outlive the decision.",
    "Models/CacheModel.swift": "#1945 — candidate dead file: CacheModel, CacheWrapper",
    "Models/DocumentStoreTypes.swift": "#3961 — candidate dead file: DocumentHierarchy. Never used in production (git log -S proves it); only its own 3 tests reference it. Surfaced when #3919 removed the file's other types. Delete or wire it — do not let this entry outlive the decision.",
    "Models/DragDropModel.swift": "#1945 — candidate dead file: DragDropModel",
    "Views/Library/Automation/ScheduleCreationSheet.swift": "#1945 — candidate dead file: ScheduleCreationSheet",
    "Views/Library/Automation/TriggerCreationSheet.swift": "#1945 — candidate dead file: TriggerCreationSheet",
    "Views/Chat/Inspector/ChatInspector+ScopedDocuments.swift": "#2955 — helper row used only by same-file ChatInspector scoped-documents view builder",
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Biography.swift": "#1945 — candidate dead file: MentionSummary",
    "Intents/FicheroShortcuts.swift": "#2017 — App Intents/Shortcuts entry point helper",
    "Views/Library/ViewModes/LibraryView+EntityFiltering.swift": "#1945 — candidate dead file: KgKindMapping (moved here from LibraryView+DisplayModes when that file was split by file_length; used only by the same-file entity-filter extension)",
    "Views/Preview/ImageViewer/ScrollWheelZoom.swift": "#1945 — candidate dead file: scroll-wheel zoom bridge types",
    "Views/Preview/PDFViewer/PageImageGrid.swift": "#1945 — candidate dead file: page image grid helper types",
    "Views/Settings/MCP/MCPToolsCatalogView.swift": "#1945 — candidate dead file: MCP tools catalog helper types",
    "Views/Settings/MCP/MCPServersSheet.swift": "#3366 — settings routing keeps legacy sheet compiled for transition/back-compat",
    "Views/Library/Notes/NotesBrowserView.swift": "#2955 — live but scanner-blind: source read by NoteServiceTests",
    "Views/Sidebar/State/ActivityDataProcessing.swift": "#1945 — candidate dead file: ActivityWorkflowGroup",
    "Views/Components/MiniToolbarComponents.swift": "#2955 — live but scanner-blind: WorkflowMiniToolbarButton exercised by #2415 tests",
    "Views/Workflow/Editor/SimpleWorkflowView.swift": "#1945 — candidate dead file: SimpleWorkflowView, SimpleWorkflow",
    "Views/Workflow/Execution/WorkflowExecutionView.swift": "#1945 — candidate dead file: workflow execution helper types",
    # (WorkflowSuggestionPolicy now referenced directly — entry dropped 2026-08-31)
    # "Models/WorkflowSuggestionPolicy.swift": "2026-08-30 — suggestion glyphs left the toolbar (Daniel's ruling) so the policy is momentarily unreferenced; the suggestions-row-INSIDE-the-bar lane is APPROVED and rewires it. Do not let this entry outlive that lane.",
    "Views/Library/ViewModes/List/LibraryView+ListView.swift": "2026-09-01 — ListRowChrome is the per-pass row-settings carrier threaded into the same-file documentRow/mailRow builders (list-scroll perf); scanner misses same-file wiring",
    "Views/Workflow/Canvas/WorkflowEdgeView+Edges.swift": "#2955 — EdgesView/PortPositionCalculator split out of WorkflowEdgeView.swift by file_length; were ALREADY unreferenced pre-split (co-located, so unflagged). Appears to be superseded dead code (edges now render via WorkflowCanvasView+EdgesLayer) — FLAG FOR DANIEL to delete/wire; grandfathered so the split lands.",
}


def code_only(text: str) -> str:
    text = BLOCK_COMMENT.sub("", text)
    return "\n".join(LINE_COMMENT.sub("", line) for line in text.splitlines())


def swift_files() -> list[Path]:
    return sorted(SWIFT_ROOT.rglob("*.swift"))


def primary_types(path: Path, source: str) -> list[str]:
    names = TYPE_DECL.findall(code_only(source))
    return [name for name in names if not is_preview_type(name)]


def is_preview_type(name: str) -> bool:
    return "Preview" in name or name.endswith("Previews")


def is_entry_or_generated(path: Path, source: str, names: list[str]) -> bool:
    rel = path.relative_to(SWIFT_ROOT).as_posix()
    if "@main" in source:
        return True
    if rel.startswith("App/") or path.name in {"FicheroApp.swift"}:
        return True
    if path.name.endswith("Generated.swift"):
        return True
    if "@objc(" in source or "NSScriptCommand" in source:
        return True
    if any(name.endswith("App") or is_preview_type(name) for name in names):
        return True
    return False


def _reached_by_extension(source: str, own_counts: Counter, total_counts: Counter) -> bool:
    """Whether this file adds a method to another type that somebody else calls.

    Narrow on purpose. It applies only to files containing an `extension` block, and only to
    `func` names — not stored or computed properties, and never a protocol requirement. A file
    holding a single self-contained `struct SomeSheet: View` has no extension block, so an
    unreferenced view is still reported, which is the case this guard exists for.
    """
    if not EXTENSION_BLOCK.search(source):
        return False
    for name in FUNC_DECL.findall(code_only(source)):
        if name in PROTOCOL_REQUIREMENTS:
            continue
        if total_counts[name] > own_counts[name]:
            return True
    return False


def scan() -> dict[str, list[str]]:
    files = swift_files()
    sources = {path: path.read_text(errors="ignore") for path in files}
    file_counts = {path: Counter(IDENTIFIER.findall(source)) for path, source in sources.items()}
    total_counts = Counter()
    for counts in file_counts.values():
        total_counts.update(counts)
    found: dict[str, list[str]] = {}

    for path in files:
        names = primary_types(path, sources[path])
        if not names or is_entry_or_generated(path, sources[path], names):
            continue

        unreferenced: list[str] = []
        for name in names:
            if total_counts[name] == file_counts[path][name]:
                unreferenced.append(name)

        if unreferenced and len(unreferenced) == len(names) and _reached_by_extension(
            sources[path], file_counts[path], total_counts
        ):
            continue

        if unreferenced and len(unreferenced) == len(names):
            rel = path.relative_to(SWIFT_ROOT).as_posix()
            found[rel] = [f"primary type(s) only declared here: {', '.join(unreferenced)}"]

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Candidate dead Swift files ({len(found)} files):\n")
        for rel, reasons in sorted(found.items()):
            tag = "known" if rel in known else "NEW"
            print(f"  [{tag}] {rel}")
            for reason in reasons:
                print(f"          - {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Dead-file guardrail: scanned {SWIFT_ROOT.relative_to(ROOT)}")
    # #4487 scan floor: on files ENUMERATED — candidates reaching zero is
    # the goal state; an empty enumeration is blindness.
    require_scan_floor(
        sum(1 for _ in SWIFT_ROOT.rglob("*.swift")), 400,
        "Swift files (884 on 2026-08-02)",
    )
    print(f"  {len(found)} candidate dead file(s); {len(known)} known backlog entries.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for rel in stale:
            print(f"      {rel}")

    if new:
        print(f"\n  ✗ {len(new)} new candidate dead Swift file(s):")
        for rel in new:
            for reason in found[rel]:
                print(f"      {rel}  ←  {reason}")
        print(
            "\nFix: remove the file, wire it from production code, or add a documented "
            f"KNOWN_VIOLATIONS entry if it is intentionally reflection-only. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No candidate dead Swift files beyond the known backlog.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SWIFT_ROOT)
    raise SystemExit(main())
