#!/usr/bin/env python3
"""Native selectable-controls guardrail.

Rule: selectable row collections should use List/Table/OutlineGroup; see docs/ROADMAP.md.

Flags SwiftUI view files that build list-like row collections as ScrollView plus
LazyVStack/VStack plus ForEach. KNOWN_VIOLATIONS is today's migration backlog,
so this script passes today and fails only on new hand-rolled row collections.

Usage:
    scripts/check_native_controls.py
    scripts/check_native_controls.py --list
    scripts/check_native_controls.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "docs/ROADMAP.md"

KNOWN_VIOLATIONS: dict[str, str] = {
    'AIProviders/AddProviderSheet+Step1.swift:33': '#1912 baseline',
    'AIProviders/ProvidersView+ProviderDetailView.swift:37': '#1912 baseline',
    'Actions/ActionDetailView.swift:10': '#1912 baseline',
    'Activity/ActivityLogView.swift:105': '#1912 baseline',
    'Activity/ActivityOverviewView+Cards.swift:25': '#1912 baseline',
    'Components/WorkflowPreviewSheet.swift:36': '#1912 baseline',
    'KnowledgeGraph/OntologyBrowser/EntitySourceGroupsView.swift:67': '#1912 baseline',
    'KnowledgeGraph/OntologyBrowser/HeuristicReviewSheet.swift:59': '#1912 baseline',
    'KnowledgeGraph/OntologyBrowser/SpeakerComparisonView.swift:25': '#1912 baseline',
    'Library/ArtifactsBrowserView.swift:161': '#1912 baseline',
    'Library/ImageEditor/ImageEditChainPanel.swift:76': '#1912 baseline',
    'Library/LibraryView+DisplayModes.swift:210': '#1912 baseline',
    'Library/PDFReadingView.swift:53': '#1912 baseline',
    'Library/WorkspaceItemPicker.swift:224': '#1912 baseline',
    'MCPServers/MCPServerDetailView.swift:17': '#1912 baseline',
    'ModelComparison/ComparisonResultView.swift:7': '#1912 baseline',
    'Notes/NotesBrowserView.swift:138': '#1912 baseline',
    'Research/ResearchTasksPane.swift:202': '#1912 baseline',
    'Research/ResearchTasksPane.swift:269': '#1912 baseline',
    'Search/SearchFiltersPanel.swift:16': '#1912 baseline',
    'Search/SearchResultsDisplay.swift:139': '#1912 baseline',
    'Workflow/WorkflowChainListView/ChainDetailContent.swift:10': '#1912 baseline',
}
APPKIT_BRIDGE_MARKERS = (
    "AttributedTextEditor",
    "MacPlainTextEditor",
    "ImageWithCursorTracking",
    "PDFKit",
    "QuickLook",
    "ScrollWheelZoom",
    "TrackingImageView",
)

ALLOWLIST_FILES = {
    # Non-list drawing/canvas or display surfaces.
    "Library/LibraryView+TableMapViews.swift",
    "Library/PageContentPane.swift",
    "Library/ArtifactPanel.swift",
    "Chat/ChatMessagesList.swift",
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")


def _strip_preview_blocks(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = text.find("#Preview", i)
        if m == -1:
            out.append(text[i:])
            break
        out.append(text[i:m])
        brace = text.find("{", m)
        if brace == -1:
            out.append(text[m:])
            break
        depth = 0
        j = brace
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        out.append("\n" * text[m:j].count("\n"))
        i = j
    return "".join(out)


def code_lines(text: str) -> list[str]:
    text = _strip_preview_blocks(_BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text))
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def is_excluded(path: Path) -> bool:
    rel = path.relative_to(VIEWS_DIR).as_posix()
    return rel in ALLOWLIST_FILES or any(marker in path.name for marker in APPKIT_BRIDGE_MARKERS)


def _matching_close(lines: list[str], start_index: int) -> int:
    depth = 0
    saw_open = False
    for idx in range(start_index, len(lines)):
        line = lines[idx]
        depth += line.count("{")
        if "{" in line:
            saw_open = True
        depth -= line.count("}")
        if saw_open and depth <= 0:
            return idx
    return min(len(lines) - 1, start_index + 80)


def violations_for(path: Path) -> list[tuple[int, str]]:
    try:
        lines = code_lines(path.read_text(errors="ignore"))
    except OSError:
        return []
    violations: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if re.search(r"\bScrollView\s*(?:\(|\{|\[)", line):
            end = _matching_close(lines, idx)
            block = "\n".join(lines[idx : end + 1])
            if re.search(r"\b(?:LazyVStack|VStack)\s*(?:\(|\{)", block) and re.search(r"\bForEach\s*\(", block):
                violations.append((idx + 1, "ScrollView + LazyVStack/VStack + ForEach row collection"))
    return violations


def scan() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(VIEWS_DIR.rglob("*.swift")):
        if is_excluded(path):
            continue
        rel = path.relative_to(VIEWS_DIR).as_posix()
        for line_no, reason in violations_for(path):
            found[f"{rel}:{line_no}"] = reason
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Native-controls guardrail offenders ({len(found)} locations):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Native-controls guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} hand-rolled row collection(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new hand-rolled row collection(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: use native List, Table, or OutlineGroup unless this is sanctioned "
            f"non-list content. Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries; clean them up when convenient.)")
    print("\nOK: no new hand-rolled selectable row collections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
