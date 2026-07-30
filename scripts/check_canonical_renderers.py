#!/usr/bin/env python3
"""Canonical-renderer guardrail for #1935.

The rule (Observable Data Layer — single renderer per domain type):

    > For each primary domain type (KnowledgeEntity, KnowledgeClaim,
    > DocumentCitation), exactly ONE canonical SwiftUI view component renders
    > it everywhere in the app. Local private struct/func alternatives that
    > duplicate the canonical shape are forbidden; only affordance-extending
    > views (edit, rename, curation controls) that *wrap* the canonical one
    > are allowed — and those must be listed in KNOWN_EXTENSIONS below.

Canonical renderers:
  - KnowledgeEntity  →  EntityRow          (EntityRowView.swift, style:.browser/.digest)
  - KnowledgeClaim   →  ClaimSummaryCard   (ClaimSummaryCardView.swift)
  - DocumentCitation →  CitationRow        (CitationListView.swift — public-ish private struct)

What this script detects (scanned outside comments + #Preview):
  - A `struct Foo: View` or `private func fooRow(…)` whose lowercased name
    contains a domain-type marker (entity/claim/citation) AND a renderer marker
    (row/card/cell/view/item) that is NOT in the canonical file OR in
    KNOWN_EXTENSIONS.
  - Any file that defines its own struct with a name matching the canonical
    renderer name (i.e., shadowing EntityRow / ClaimSummaryCard / CitationRow).

NOT flagged:
  - The canonical renderer files themselves.
  - KNOWN_EXTENSIONS entries (view-local functions/structs that wrap or extend
    the canonical with edit affordances — documented with a reason and issue #).
  - ArtifactEntityViews / EntityLozenge / ArtifactEntityCell (render raw
    extraction strings, not KnowledgeEntity objects — intentionally different).
  - Stub/preview/test files.

Usage:
    python3 scripts/check_canonical_renderers.py          # exit 1 on violations
    python3 scripts/check_canonical_renderers.py --list   # list all findings
    python3 scripts/check_canonical_renderers.py -h       # this help

Exit codes:
    0  all findings are in KNOWN_EXTENSIONS
    1  a new local renderer was added without being listed here
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"

# Canonical renderer source files — skip scanning these.
CANONICAL_FILES = {
    "EntityRowView.swift",
    "ClaimSummaryCardView.swift",
    "ClaimSummaryCard+Details.swift",
    "ClaimSummaryCard+Provenance.swift",
    "CitationListView.swift",
}

# Domain-type markers (lowercased) and renderer-shape markers (lowercased).
DOMAIN_MARKERS = ("entity", "claim", "citation")
RENDERER_MARKERS = ("row", "card", "cell", "item")

# Structs that deliberately shadow or extend the canonical renderers.
# Each entry: (filename_substring, symbol_pattern_substring, reason_and_issue)
# Symbol pattern is matched case-insensitively against the detected name.
KNOWN_EXTENSIONS: list[tuple[str, str, str]] = [
    # iOS List refactor (#2501): shared row builder wrapping the canonical
    # EntityRow in LibrarySelectableRow selection chrome — renders nothing
    # domain-specific itself; trips the `*Row` heuristic only.
    (
        "LibraryView+ListView.swift",
        "entityListRow",
        "Selection-chrome wrapper delegating to the canonical EntityRow "
        "(#2501 iOS List container split).",
    ),
    # KG section claim row: a call-site wrapper that forwards straight to the
    # canonical EntityKindRow (it only binds the section's many bindings once
    # instead of at every ForEach site). No local rendering — it trips the
    # `*Row` name heuristic, not the rule (#1935).
    (
        "KnowledgeGraphInspectorSection+Views.swift",
        "kgClaimRow",
        "Thin wrapper that delegates to the canonical EntityKindRow — binds the "
        "section's arguments in one place; renders nothing itself (#1935).",
    ),
    # Inspector entity row: extends EntityRow.browser with inline-rename,
    # curation badge, and entity description field (#1935 audit 2026-06-14).
    (
        "DocumentInspectorEntitiesTab+Rows.swift",
        "entityRow",
        "Inspector entity row adds rename + curation badge + description — "
        "affordance-extended wrapper, not a duplicate (#1935).",
    ),
    # NOTE: the RelatedClaims entry ("row(for claim") was removed 2026-07-28 as
    # DEAD (#4174 audit). Its fragment contained "(" and a space, which cannot
    # occur in a captured Swift identifier, so it never matched. The symbol it
    # aimed at — `private func row(for claim: EntityService.SimilarClaim)` — is
    # captured as the name `row`, which carries a renderer marker but no domain
    # marker, so `_is_renderer_name` never flags it and no exemption is needed.
    # Inspector citations tab: renders raw DocumentCitation (no direction field).
    # CitationListView.CitationRow uses CitationItem (DocumentCitation + direction).
    (
        "DocumentInspectorInfoTab+Citations.swift",
        "citationRow",
        "Renders raw DocumentCitation without direction metadata — CitationRow "
        "requires a CitationItem wrapper (#1935).",
    ),
    # OntologyBrowser+List entityRow wrapper: thin function that calls the canonical
    # EntityRow(entity:, claimCount:) and adds .tag(entity.id) + .contextMenu {}.
    # Not a duplicate — it IS the canonical renderer with context-menu decoration.
    (
        "OntologyBrowser+List.swift",
        "entityRow",
        "Thin wrapper: calls EntityRow(entity:, claimCount:) directly, adds "
        ".tag() and .contextMenu{}. Delegates to canonical renderer (#1935).",
    ),
    # ClaimReviewQueueSheet claimRow: a Toggle-bearing selection row for the review
    # queue batch-select UI. Not display — it's a checkbox row for claim approval.
    # ClaimSummaryCard renders claim CONTENT; this renders a claim SELECTION widget.
    (
        "ClaimReviewQueueSheet.swift",
        "claimRow",
        "Renders a Toggle checkbox for batch-selection in the review queue — "
        "a selection affordance, not a content renderer. Incompatible with "
        "ClaimSummaryCard's display-only shape (#1935).",
    ),
    # ArtifactEntityCell: renders RAW extraction strings (artifact text snippets),
    # not KnowledgeEntity objects. Completely different data type and display purpose.
    (
        "ArtifactEntityViews.swift",
        "ArtifactEntityCell",
        "Renders raw artifact extraction strings, not KnowledgeEntity objects. "
        "EntityRow requires a KnowledgeEntity; these are pre-entity text snippets "
        "from the extraction pipeline (#1935).",
    ),
    # EntityKindRow: 400+ line inspector view that shows an entity's claims inline
    # with curation bulk-actions, inline editing, merge, approve/reject/suppress.
    # This is the entity's CLAIM INSPECTOR, not an entity list row. EntityRow is
    # for browsing entities; EntityKindRow is for curating the claims OF an entity.
    (
        "EntityKindRow.swift",
        "EntityKindRow",
        "Entity claims inspector (curation affordances: merge, approve/reject/"
        "suppress, edit, bulk actions). Different scope from EntityRow (entity "
        "list browsing). Affordance-extended, not a duplicate (#1935).",
    ),
]

# Patterns that identify local struct/func renderer definitions.
# We look for: `struct FooRow: View`, `struct FooCard: View`, or
# `private func fooRow(`, `private func fooCell(` etc.
_STRUCT_RE = re.compile(
    r"^\s*(?:private\s+)?struct\s+(\w+)\s*:\s*View", re.MULTILINE
)
_FUNC_RE = re.compile(
    r"^\s*(?:private\s+)?func\s+(\w+)\s*\(", re.MULTILINE
)


def _strip_comments_and_previews(source: str) -> str:
    """Remove block comments and #Preview { } blocks to avoid false positives."""
    # Remove /* … */ block comments
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Remove // line comments
    source = re.sub(r"//[^\n]*", "", source)
    # Remove #Preview { … } blocks (brace-counting is tricky; rough removal)
    source = re.sub(r"#Preview\b[^{]*\{.*?\n\}", "", source, flags=re.DOTALL)
    return source


def _is_renderer_name(name: str) -> bool:
    low = name.lower()
    if low.startswith(("make", "build")):
        return False
    return any(d in low for d in DOMAIN_MARKERS) and any(r in low for r in RENDERER_MARKERS)


def _matching_entry(rel_path: str, symbol: str) -> int | None:
    """Index of the first KNOWN_EXTENSIONS entry covering this symbol, else None."""
    for index, (file_frag, sym_frag, _reason) in enumerate(KNOWN_EXTENSIONS):
        if file_frag in rel_path and sym_frag.lower() in symbol.lower():
            return index
    return None


def _is_known_extension(rel_path: str, symbol: str) -> str | None:
    """Return the justification string if this is a known extension, else None."""
    index = _matching_entry(rel_path, symbol)
    return KNOWN_EXTENSIONS[index][2] if index is not None else None


def entry_matches() -> list[list[str]]:
    """Per-KNOWN_EXTENSIONS-entry list of the symbols it covered.

    Entries are matched by SUBSTRING, not exact key, so an entry that covers
    nothing is not merely untidy — it is a standing wildcard that will grant
    cover to any future symbol whose name happens to contain the fragment.
    Reporting both the empty entries and the over-broad ones is what keeps the
    baseline shrinking instead of silently widening (#4201 sweep).
    """
    matches: list[list[str]] = [[] for _ in KNOWN_EXTENSIONS]
    for finding in scan():
        index = _matching_entry(finding["file"], finding["symbol"])
        if index is not None:
            matches[index].append(f"{finding['file']}::{finding['symbol']}")
    return matches


def scan() -> list[dict]:
    findings: list[dict] = []

    for swift_file in sorted(VIEWS_DIR.rglob("*.swift")):
        if swift_file.name in CANONICAL_FILES:
            continue
        if "Tests" in swift_file.parts or "Preview" in swift_file.name:
            continue

        source = swift_file.read_text(encoding="utf-8", errors="replace")
        cleaned = _strip_comments_and_previews(source)
        rel = str(swift_file.relative_to(ROOT / "fichero" / "fichero" / "Views"))

        for match in list(_STRUCT_RE.finditer(cleaned)) + list(_FUNC_RE.finditer(cleaned)):
            name = match.group(1)
            if not _is_renderer_name(name):
                continue
            known_reason = _is_known_extension(rel, name)
            findings.append(
                {
                    "file": rel,
                    "symbol": name,
                    "kind": "struct" if "struct" in match.group(0) else "func",
                    "known": known_reason is not None,
                    "reason": known_reason or "",
                }
            )

    return findings


def main(argv: list[str]) -> int:
    list_mode = "--list" in argv or "-l" in argv
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0

    findings = scan()
    new_violations = [f for f in findings if not f["known"]]
    known = [f for f in findings if f["known"]]

    print(f"Canonical-renderer guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(
        f"  {len(new_violations)} new violation(s); "
        f"{len(known)} known extension(s).\n"
    )

    if list_mode:
        if known:
            print("Known extensions (legitimate — documented in KNOWN_EXTENSIONS):\n")
            for f in known:
                tag = f["kind"]
                print(f"  [{tag}] {f['file']}::{f['symbol']}")
                print(f"         {f['reason']}")
            print()
        if new_violations:
            print("NEW violations (not in KNOWN_EXTENSIONS):\n")
            for f in new_violations:
                tag = f["kind"]
                print(f"  [NEW {tag}] {f['file']}::{f['symbol']}")
            print()

    matches = entry_matches()
    stale = [i for i, hits in enumerate(matches) if not hits]
    broad = [i for i, hits in enumerate(matches) if len(hits) > 1]

    if stale:
        print(f"  {len(stale)} KNOWN_EXTENSIONS entr(ies) match nothing; remove them:")
        for index in stale:
            file_frag, sym_frag, _ = KNOWN_EXTENSIONS[index]
            print(f"      [{index}] {file_frag} :: {sym_frag}")
        print(
            "  (These are not inert: matching is by SUBSTRING, so a dead entry\n"
            "   silently exempts any future symbol containing that fragment.)\n"
        )

    if broad:
        print(f"  {len(broad)} KNOWN_EXTENSIONS entr(ies) cover MORE THAN ONE symbol:")
        for index in broad:
            file_frag, sym_frag, _ = KNOWN_EXTENSIONS[index]
            print(f"      [{index}] {file_frag} :: {sym_frag} -> {', '.join(matches[index])}")
        print("  (Narrow the fragment if the extra matches were not intended.)\n")

    if new_violations:
        print(
            "✗ Local domain renderer(s) found outside canonical files.\n"
            "  Either:\n"
            "  (a) Delegate to EntityRow / ClaimSummaryCard / CitationRow, OR\n"
            "  (b) Add an entry to KNOWN_EXTENSIONS in this script with a reason.\n"
            "  See #1935 for guidance."
        )
        return 1

    print("✓ No new local domain renderers beyond the known extensions.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
