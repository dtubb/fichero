#!/usr/bin/env python3
"""Native selectable-controls guardrail.

Rule: selectable row collections should use List/Table/OutlineGroup; see agents/ROADMAP.md.

Flags SwiftUI view files that build list-like row collections as ScrollView plus
LazyVStack/VStack plus ForEach. KNOWN_VIOLATIONS is today's migration backlog,
so this script passes today and fails only on new hand-rolled row collections.

Usage:
    scripts/check_native_controls.py
    scripts/check_native_controls.py --list
    scripts/check_native_controls.py --help
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "agents/ROADMAP.md"

# Rekeyed to stable content signatures so unrelated line shifts do not churn the backlog.
KNOWN_VIOLATIONS: dict[str, str] = {
    "Activity/ActivityOverviewView+Cards.swift#76a86e98cc": "#1912 baseline",
    "KnowledgeGraph/OntologyBrowser/EntitySourceGroupsView.swift#c6a609c38d": "#1912 baseline",
    "KnowledgeGraph/OntologyBrowser/HeuristicReviewSheet.swift#aa939bcbf4": "#1912 baseline",
    "KnowledgeGraph/OntologyBrowser/SpeakerComparisonView.swift#ffffcf8a29": "#1912 baseline",
    "Preview/ImageEditor/ImageEditChainPanel.swift#83a0175036": "#1912 baseline",
    "Library/LibraryView+DisplayModes.swift#19c3b271df": "#1912 baseline (rehashed: #3705 .draggable; #3875 selection-fill; #3868 extracted a value-typed selectable row wrapper; the collection itself is unchanged)",
    "Library/Workspace/WorkspaceItemPicker.swift#2e87b93a6b": "#1912 baseline",
    "Chat/Research/ResearchTasksPane.swift#1d731da4e7": "#1912 baseline (shifted by store migration)",
    "Chat/Research/ResearchTasksPane.swift#f50acbd404": "#1912 baseline (shifted by store migration)",
    "Library/Search/SearchFiltersPanel.swift#3c0b0dafd9": "#1912 baseline",
    "Workflow/WorkflowChainListView/ChainDetailContent.swift#c804133262": "#1912 baseline",
}

ALLOWLIST_FILES = {
    # Non-list drawing/canvas or display surfaces.
    "Library/LibraryView+TableMapViews.swift",
    "Library/PageContentPane.swift",
    "Library/ArtifactPanel.swift",
    "Chat/ChatMessagesList.swift",
    # Form-based settings detail views - Form+Section+ForEach is proper form usage,
    # not a hand-rolled row collection.
    "Settings/AIProviders/ProvidersView+ProviderDetailView.swift",
    "Settings/MCPServers/MCPServerDetailView.swift",
    # Free-form detail / log / grid surfaces - not selectable row collections.
    "Library/Actions/ActionDetailView.swift",  # mixed detail content; ForEach is for a tag-chip FlowLayout
    "Activity/ActivityLogView.swift",  # streaming log viewer with auto-scroll
    "Chat/ModelComparison/ComparisonResultView.swift",  # LazyVGrid card grid for model results
    "Library/Search/SearchResultsDisplay.swift",  # icon mode uses LazyVGrid; list mode already uses native List
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
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = _strip_preview_blocks(text)
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


def _normalized_snippet(lines: list[str], start_index: int) -> tuple[int, str]:
    end = _matching_close(lines, start_index)
    snippet = "\n".join(lines[start_index : end + 1])
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return end, snippet


def _signature_key(rel: str, snippet: str) -> str:
    digest = hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


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
        try:
            lines = code_lines(path.read_text(errors="ignore"))
        except OSError:
            continue
        rel = path.relative_to(VIEWS_DIR).as_posix()
        for line_no, _reason in violations_for(path):
            end_idx, snippet = _normalized_snippet(lines, line_no - 1)
            found[_signature_key(rel, snippet)] = (
                f"ScrollView + LazyVStack/VStack + ForEach row collection (lines {line_no}-{end_idx + 1})"
            )
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
        print(
            "\nFix: remove the now-clean entries listed above from KNOWN_VIOLATIONS. A stale "
            "baseline entry rots into a silent gate hole — the ratchet must tighten as "
            f"violations are fixed. Rule pointer: {RULE_DOC}."
        )
        return 1
    print("\nOK: no new hand-rolled selectable row collections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
