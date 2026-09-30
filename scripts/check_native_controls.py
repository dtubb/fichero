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
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "agents/ROADMAP.md"

# Rekeyed to stable content signatures so unrelated line shifts do not churn the backlog.
KNOWN_VIOLATIONS: dict[str, str] = {
    # 2026-08-28 capability bar: both popovers stack a heading, a description,
    # engine-provided badges and an expandable prompt block per entry. A List
    # would impose row selection and separators on content whose whole purpose
    # is to be read before choosing — and the expand gesture must not select.
    "Shell/Toolbar/WorkflowToolsPopover.swift#2d76b922c8": "2026-08-28 tools browser: searchable tool cards with expandable prompts, not selectable rows (re-pinned 2026-08-30 after card rework)",
    "Shell/Toolbar/ModelChipToolbarItem.swift#0b4ae6d6c7": "2026-08-29 model picker popover (rehashed 2026-09-01 by the model-routing pass, 2026-09-04 by the pickable-model fix in 3ed311ca3, and 2026-09-17/#4902 by the SharedModelRow swap + an explanatory comment): logo+pricing+vision rows in a fixed-height popover; List chrome misbehaves in popovers and the concrete-row perf fix (333ms stall) depends on this structure. Same block, same reasons — the signature moved, the sanction did not",
    "Reader/MultiSelectionReaderView.swift#59b0e99ae5": "2026-08-23 multi-selection reader: continuous transcript SECTIONS under pinned headers — prose, not a row collection; List would impose row selection and separators on reading text",
    # The next five read only "#1912 baseline" until 2026-09-27; each was read and given
    # its reason. DESIGN = not a row collection; DEBT = should become a List.
    "Activity/Overview/ActivityOverviewView+Cards.swift#d6f20143ab": "DESIGN: a horizontally scrolling document x step GRID with a fixed header row, not a list of rows; List scrolls one axis and has no column header",
    "Library/ViewModes/Graph/Ontology/Entity/EntitySourceGroupsView.swift#c6a609c38d": "DEBT: claims grouped under per-source headers, expressible as List { Section }; its only host is the unmounted EntityDetailView (#4828), so migrate or retire with it",
    "Library/ViewModes/Graph/Ontology/Claim/HeuristicReviewSheet.swift#aa939bcbf4": "DEBT: read-only prediction cards (no per-row tap or selection); no caller outside #4828's orphaned KG views, so migrate or retire with them",
    "Library/ViewModes/Graph/Ontology/SpeakerComparisonView.swift#ffffcf8a29": "DESIGN: per-speaker comparison CARDS under a title, not selectable rows; only its previews construct it today (#4828)",
    "Preview/ImageEditor/ImageEditChainPanel.swift#83a0175036": "DEBT, the #4483 shape: an ordered edit-step list with HAND-ROLLED selection (a Button in stepRow sets selectedStepIndex). check_native_row_containers cannot see it because the tap sits in a helper; List(selection:) would give arrows, focus and onMove",
    "Library/ViewModes/List/LibraryView+ListView.swift#5acecef157": "DESIGN (#4160): ScrollView is required for the list mode's keyboard handling — List consumes arrow keys before .onKeyPress (rehashed by the #2501 iOS List split, by #3322's 'No date' section, and by the 2026-09-01 per-pass row-chrome hoist — same sanctioned container)",
    # Miller columns (#4160 step 4): List is NSTableView-backed and consumes
    # arrow keys before .onKeyPress — the browser's whole keyboard model
    # (up/down in the active column, left/right BETWEEN columns, one shared
    # cursor) runs through body-level key handlers, and a per-column List
    # would own per-column selection, breaking the single shared set. The
    # constraint is stated in-file at the collection site.
    # Hash re-baselined by #4474 (drop closure renamed) and again by the
    # 2026-08-04 wave (#4514 read-only refusal + #4516 shared icon ladder
    # edited rows inside the block). Same sanctioned violation, same lines —
    # only the content hash moved.
    "Library/ViewModes/Columns/LibraryView+ColumnsView.swift#4e411eba60": "#4160 step 4 (same keyboard constraint as the list-mode entry; justified in-file — re-hashed 2026-08-09 twice, 2026-08-10 by the top-level-rooting/preview-width edits, and 2026-09-30 by the simultaneous double-tap (#5276) inside the same grandfathered block)",
    "Library/Workspace/WorkspaceItemPicker.swift#2e87b93a6b": "DEBT: a picker of workspace folders where each row is a Button — a tappable row collection that List would give arrows and focus to (tap sits in folderRow, so check_native_row_containers cannot see it)",
    # Same two content hashes as the +Views.swift entries they replace — only
    # the PATH moved. The file was split at its own MARK boundary when
    # accessibility labels pushed it past the 400-line limit (#4484), and the
    # unchanged hashes are independent proof that split was a pure move.
    "Chat/Research/ResearchTasksPane+Tabs.swift#1d731da4e7": "DESIGN: verification-checklist CARDS (each holds its own items and a composer), not selectable rows (moved from +Views.swift by the #4484 split; hash unchanged)",
    "Chat/Research/ResearchTasksPane+Tabs.swift#f50acbd404": "DESIGN: research-note CARDS above a composer, read and edited in place, not selectable rows (moved from +Views.swift by the #4484 split; hash unchanged)",
    "Workflow/Library/WorkflowChainListViewParts/ChainDetailContent.swift#c804133262": "DESIGN: a detail PAGE (title, description, then the chain's steps) in one scroll, not a row collection; hosted by ChainDetailSheet and ChainEditorView",
    # Data-mode reading surfaces (2026-08-14): NO selection model (open is
    # double-click/context menu only), and SwiftUI's NSTableView-backed List
    # SIGTRAPed in ViewListTree.visitItem on this exact content under the
    # preview host (Fichero-2026-08-14-0933xx.ips ×3). Reason also recorded
    # in-file and in native_row_containers_allowlist.json. Revisit List if a
    # selection model arrives.
    "Library/ViewModes/Dataset/Timeline/DatasetTimelineView.swift#1c431f5c23": "2026-08-14 List SIGTRAP; re-hashed 2026-08-19 by the SelectionGrammar clicks + Full Text cap lift (#4598) — same sanctioned block. NOTE: rows now multi-select, so the List constraint deserves a revisit next preview session",
    # 2026-09-20: the SAME model-picker popover shape already sanctioned for
    # ModelChipToolbarItem.swift above (logo/pricing/vision SharedModelRow
    # rows in a fixed-height popover) — Chat's own toolbar model picker,
    # not a new pattern. Same reason applies: List chrome misbehaves in
    # popovers, and the concrete-row perf fix that shape depends on assumes
    # this structure.
    "Chat/ChatViewToolbar.swift#2a472b0532": "2026-09-20: same fixed-height SharedModelRow popover shape as ModelChipToolbarItem.swift — List misbehaves in popovers; same reason, different toolbar",
    # 2026-09-20: a 2D coverage MATRIX (model rows × language columns),
    # scrolling BOTH axes with a frozen header row — not a selectable row
    # list at all (no tap target, no selection state on a cell). `Table`
    # assumes one fixed column set known ahead of render and per-row
    # selection; this view's column set is the CHOSEN language set (variable,
    # user-editable via the picker below it) and no row is ever selected.
    # Same "no selection model" reasoning as DatasetTimelineView's own entry.
    "LooveCoverage/LooveCoverageView.swift#e6c345f987": "2026-09-20: a read-only coverage matrix (rows x variable language columns), both-axis scroll, no selection model — Table assumes a fixed column set and row selection, neither of which applies here",
}

ALLOWLIST_FILES = {
    # Non-list drawing/canvas or display surfaces.
    "Library/ViewModes/LibraryView+TableMapViews.swift",
    "Library/PageContentPane.swift",
    "Library/ArtifactPanel.swift",
    "Chat/ChatMessagesList.swift",
    # Form-based settings detail views - Form+Section+ForEach is proper form usage,
    # not a hand-rolled row collection.
    "Settings/AI/AIProviders/ProvidersView+ProviderDetailView.swift",
    "Settings/MCP/MCPServerDetailView.swift",
    # Free-form detail / log / grid surfaces - not selectable row collections.
    "Library/Actions/ActionDetailView.swift",  # mixed detail content; ForEach is for a tag-chip FlowLayout
    "Activity/ActivityLogView.swift",  # streaming log viewer with auto-scroll
    "Chat/ModelComparison/ComparisonResultView.swift",  # LazyVGrid card grid for model results
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
    for path in sorted(scan_rglob(VIEWS_DIR, "*.swift")):
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
