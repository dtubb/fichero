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

# Current candidate-dead backlog. Drop entries as files are removed or wired.
KNOWN_VIOLATIONS: dict[str, str] = {
    "Models/CacheModel.swift": "#1945 — candidate dead file: CacheModel, CacheWrapper",
    "Models/DocumentStoreTypes.swift": "#3961 — candidate dead file: DocumentHierarchy. Never used in production (git log -S proves it); only its own 3 tests reference it. Surfaced when #3919 removed the file's other types. Delete or wire it — do not let this entry outlive the decision.",
    "Models/DragDropModel.swift": "#1945 — candidate dead file: DragDropModel",
    "Views/Actions/ActionPickerView.swift": "#1945 — candidate dead file: action picker helper types",
    "Views/Automation/ScheduleCreationSheet.swift": "#1945 — candidate dead file: ScheduleCreationSheet",
    "Views/Automation/ScheduleEditorView+Category.swift": "#2955 — helper enum used only by same-file ScheduleEditorView extension; scanner misses local view/helper wiring",
    "Views/Automation/TriggerCreationSheet.swift": "#1945 — candidate dead file: TriggerCreationSheet",
    "Views/Chat/ChatInspector+ScopedDocuments.swift": "#2955 — helper row used only by same-file ChatInspector scoped-documents view builder",
    "Views/ContentView+ViewBuilders.swift": "#2955 — ReadingPaneView is instantiated only inside same-file ContentView builders; scanner blind spot",
    "Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Provenance.swift": "#1945 — candidate dead file: ProvenanceBadge",
    "Views/KnowledgeGraph/OntologyBrowser/EntityDetailView+Biography.swift": "#1945 — candidate dead file: MentionSummary",
    "Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser+Toolbar.swift": "#1945 — candidate dead file: EntityKindChip",
    "Intents/FicheroShortcuts.swift": "#2017 — App Intents/Shortcuts entry point helper",
    "Views/Library/LibraryView+ColumnConfig.swift": "#1945 — candidate dead file: ColumnDefinition",
    "Views/Library/LibraryView+DisplayModes.swift": "#1945 — candidate dead file: KgKindMapping",
    "Views/Preview/ImageViewer/ScrollWheelZoom.swift": "#1945 — candidate dead file: scroll-wheel zoom bridge types",
    "Views/Library/Reading/PageImageGrid.swift": "#1945 — candidate dead file: page image grid helper types",
    "Views/Library/Workspace/CollectionWorkspaceStub.swift": "#1945 — candidate dead file: workspace stub helper",
    "Views/Shell/PaneVisibility.swift": "#1945 — candidate dead file: pane visibility helpers",
    "Views/Sidebar/SidebarView+LibraryHeaderHelpers.swift": "#1945 — candidate dead file: library header helper row",
    "Views/Workflow/WorkflowEditor+Actions.swift": "#1945 — candidate dead file: workflow completion helper",
    "Views/MCPServers/MCPToolsCatalogView.swift": "#1945 — candidate dead file: MCP tools catalog helper types",
    "Views/MCPServers/MCPServersSheet.swift": "#3366 — settings routing keeps legacy sheet compiled for transition/back-compat",
    "Views/Menu/AddItemMenu.swift": "#2955 — live but scanner-blind: sole toolbar-evidence for Link/Copy/Add-Files in the action-surface matrix",
    "Views/Menu/ImagePreviewMenuCommands.swift": "#1945 — candidate dead file: MagnifierLimits",
    "Views/Notes/NotesBrowserView.swift": "#2955 — live but scanner-blind: source read by NoteServiceTests",
    "Views/Search/SearchArrowKeyNavigation.swift": "#2955 — file stays live via View.arrowKeyResultNavigation extension; primary helper types are local-only",
    "Views/Search/SearchFiltersPanel.swift": "#1945 — candidate dead file: SearchFiltersPanel",
    "Views/Settings/AISettingsView+Helpers.swift": "#1945 — candidate dead file: TierCapability",
    "Views/Sidebar/ActivityDataProcessing.swift": "#1945 — candidate dead file: ActivityWorkflowGroup",
    "Views/Sidebar/SidebarItemRow+Drop.swift": "#2955 — file stays live via SidebarItemRow drop-handling extension; primary helper types are local-only",
    "Views/Sidebar/SidebarView+ActivityRows.swift": "#1945 — candidate dead file: ActivityRunGridCell",
    "Views/Sidebar/SidebarView+UnifiedLibrarySections.swift": "#1945 — candidate dead file: UnifiedLibraryBuckets",
    "Views/Toolbars/MiniToolbarComponents.swift": "#2955 — live but scanner-blind: WorkflowMiniToolbarButton exercised by #2415 tests",
    "Views/Workflow/DynamicConfigView+FieldRendering.swift": "#1945 — candidate dead file: DynamicFolderPickerOption",
    "Views/Workflow/SimpleWorkflowView.swift": "#1945 — candidate dead file: SimpleWorkflowView, SimpleWorkflow",
    "Views/Workflow/WorkflowExecutionView.swift": "#1945 — candidate dead file: workflow execution helper types",
    "Views/Workflow/WorkflowInspector+DataLoading.swift": "#2955 — file stays live via WorkflowInspector data-loading extension; primary helper enum is local-only",
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


if __name__ == "__main__":
    raise SystemExit(main())
