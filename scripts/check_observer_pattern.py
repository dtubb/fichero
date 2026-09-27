#!/usr/bin/env python3
"""Observer-pattern guardrail for SwiftUI Views.

Rule (see docs/contributor_manual/architecture/fichero/observable_data_layer.md §1):

    A view observes an @Observable store via @Environment(Type.self).
    It does not use legacy @EnvironmentObject / @StateObject service wiring,
    it does not reach into LibraryManager.shared.globalLibrary directly, and it
    does not wire its own Combine observation loop around a store/service.

This script scans fichero/fichero/Views/**/*.swift and ratchets the current
backlog. KNOWN_VIOLATIONS is today's baseline, so the script passes on the
current tree and fails only on NEW offenders.

Usage:
    python3 scripts/check_observer_pattern.py
    python3 scripts/check_observer_pattern.py --list
    python3 scripts/check_observer_pattern.py --help

Exit codes:
    0  no new violations (and no stale KNOWN_VIOLATIONS entries)
    1  a new observer-pattern offender was found
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from collections import Counter
from pathlib import Path
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "docs/contributor_manual/architecture/fichero/observable_data_layer.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")

PATTERN_LABELS: dict[str, str] = {
    "environment-object": "@EnvironmentObject",
    "environment-object-injection": ".environmentObject(",
    "stateobject-service": "@StateObject …Service()",
    "observableobject-view-model": "class : ObservableObject",
    "combine-store-observation": "$publisher + sink/cancellables",
    "direct-client-api": "client.api.",
    "direct-library-manager": "LibraryManager.shared.globalLibrary",
}

# Same exemption, same reason, as `check_view_endpoint_access.py`'s
# `NON_TRANSPORT_STATEOBJECT_SERVICES` (2026-09-27): the `stateobject-service`
# pattern is a NAME heuristic, and `BonjourDiscoveryService` browses the LAN
# via `NetServiceBrowser`, never a backend endpoint. Duplicated rather than
# imported — the two guards are independent scripts by this repo's own
# convention, and a shared constant across them would be its own small
# coupling for two lines of names.
NON_TRANSPORT_STATEOBJECT_SERVICES = ("BonjourDiscoveryService",)

# Post-#2960 baseline. The @Observable foundation flip (#2960/#1863) cleared
# every @EnvironmentObject/.environmentObject/@StateObject-service/ObservableObject
# offender. These remaining entries are UNRELATED anti-patterns still on the
# backlog: direct `LibraryManager.shared.globalLibrary` reads, `client.api.`
# access, and `client.api.` direct reads. (#3743 converted FeatureManager to
# @Observable, so its former @EnvironmentObject consumers are no longer offenders.)
#
# Eleven entries checked and dropped 2026-09-27 (found already clean by the
# scan, verified individually rather than dropped on the scan's say-so alone):
# `OntologyBrowser.swift` and `OntologyBrowser+Toolbar.swift` are GONE — retired
# with the Knowledge Graph view mode (#4705 increment 3), a different fact from
# a migration; the other nine (ClaimSummaryCard+Details, ContradictionTriageSheet,
# EntityDetailView+Audit/+Biography/+Metadata, EntityMergeSheet,
# EntitySourceGroupsView, EntitySplitSheet, NewEntitySheet) still exist and read
# `@Environment(...)` today, with none of the four anti-patterns in their text —
# genuinely migrated, presumably in the #2960/#1863 flip this block's own
# comment already names, just never pruned once it landed.
# Every entry is the same anti-pattern, `LibraryManager.shared.globalLibrary`, and until
# 2026-09-27 all ten shared one pasted reason naming three patterns ("globalLibrary /
# client.api. / FeatureManager") that nine of them do not have. Read per file, they split
# into three kinds — sanctioned, a fallback, and two that use the global library as their
# ONLY source (#5133, one of which WRITES to it).
KNOWN_VIOLATIONS: dict[str, str] = {
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarDragID.swift": (
        "SANCTIONED (#4123): a Transferable export closure runs outside the SwiftUI "
        "environment, so the drag-out file promise can only resolve the library through "
        "LibraryManager at export time (fallback after the row's own library)"
    ),
    "fichero/fichero/Views/Shell/ContentView/ContentView+SearchResults.swift": (
        "#4106: resolves the window's ACTIVE library at call time, `?? globalLibrary` as the "
        "fallback — " + 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal'
    ),
    "fichero/fichero/Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift": (
        "import target: active library first, `?? globalLibrary` fallback — " + 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal'
    ),
    "fichero/fichero/Views/Library/ViewModes/Graph/KGMapView.swift": 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal',
    "fichero/fichero/Views/Library/ViewModes/Graph/KGTimelineView.swift": 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal',
    "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView.swift": 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal',
    "fichero/fichero/Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift": (
        "thumbnail storage: the injected StorageService first, `globalLibrary` fallback kept "
        "for the Spatial-room path — " + 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal'
    ),
    "fichero/fichero/Views/Library/ViewModes/Canvas/2D/Legacy/SpatialNodeThumbnail.swift": (
        "`storageService ?? globalLibrary` in a legacy 2D thumbnail — " + 'FALLBACK only: reads the injected @Environment service first and falls back to `globalLibrary` for hosts that inject none — which silently reads the wrong library (#4461 shape). Drop when every host injects and the fallback becomes a refusal'
    ),
    "fichero/fichero/Views/Components/NodeClassPicker.swift": (
        "#5133 DEFECT: lists node classes from `globalLibrary` as its ONLY source, so a "
        "workflow in any other library shows the global library's classes"
    ),
    "fichero/fichero/Views/Workflow/Nodes/NodeConfigs/ExtractEntitiesNodeConfig.swift": (
        "#5133 DEFECT: loads, ADDS and REMOVES custom entity types on `globalLibrary` as its "
        "ONLY source, so editing a workflow in another library writes the global library"
    ),
}



def _strip_preview_blocks(text: str) -> str:
    """Remove `#Preview { … }` blocks so preview-only scaffolding stays out."""
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
        i = j
    return "".join(out)


def code_only(text: str) -> str:
    """Source with comments and preview scaffolding removed."""
    text = _BLOCK_COMMENT.sub("", text)
    text = "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())
    return _strip_preview_blocks(text)


def _detect_patterns(src: str) -> list[str]:
    """Return the observer-pattern anti-patterns found in one file."""
    found: list[str] = []

    if re.search(r"(?<!\w)@EnvironmentObject\b", src):
        found.append("environment-object")

    if re.search(r"\.environmentObject\s*\(", src):
        found.append("environment-object-injection")

    state_object_service = re.compile(
        r"@StateObject[^\n=]*=\s*([A-Za-z_][A-Za-z0-9_]*Service(?:Generated)?)\s*\("
    )
    if any(
        match.group(1) not in NON_TRANSPORT_STATEOBJECT_SERVICES
        for match in state_object_service.finditer(src)
    ):
        found.append("stateobject-service")

    if re.search(r"^\s*(?:final\s+)?class\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*ObservableObject\b", src, re.M):
        found.append("observableobject-view-model")

    if re.search(r"\.\$[A-Za-z_][A-Za-z0-9_]*", src) and (
        re.search(r"\.sink\s*\(", src)
        or re.search(r"\bcancellables\b", src)
        or re.search(r"\.store\(in:\s*&cancellables\)", src)
    ):
        found.append("combine-store-observation")

    if re.search(r"\bclient\.api\.", src):
        found.append("direct-client-api")

    if re.search(r"\bLibraryManager\.shared\.globalLibrary\b", src):
        found.append("direct-library-manager")

    return found


def scan() -> dict[str, list[str]]:
    """Repo-relative file path -> list of observer-pattern violations."""
    found: dict[str, list[str]] = {}
    for path in sorted(scan_rglob(VIEWS_DIR, "*.swift")):
        try:
            src = code_only(path.read_text(errors="ignore"))
        except OSError:
            continue
        patterns = _detect_patterns(src)
        if patterns:
            found[path.relative_to(ROOT).as_posix()] = patterns
    return found


def _summarize(found: dict[str, list[str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for patterns in found.values():
        counts.update(patterns)
    return {slug: counts[slug] for slug in PATTERN_LABELS}


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)
    summary = _summarize(found)

    if "--list" in sys.argv[1:]:
        print(f"Observer-pattern guardrail offenders ({len(found)} files):\n")
        print("Summary by anti-pattern:")
        for slug, label in PATTERN_LABELS.items():
            print(f"  {label}: {summary[slug]}")
        print()
        for rel, patterns in found.items():
            tag = "known" if rel in known else "NEW"
            labels = ", ".join(PATTERN_LABELS[slug] for slug in patterns)
            print(f"  [{tag}] {rel}")
            print(f"          - {labels}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    # #4487 scan floor: 582 view files on 2026-08-02.
    require_scan_floor(
        sum(1 for _ in scan_rglob(VIEWS_DIR, "*.swift")), 291, "view files (582 on 2026-08-02)"
    )
    print(f"Observer-pattern guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} file(s) with observer-pattern violations; {len(known)} known backlog entries.")
    print("  Summary by anti-pattern:")
    for slug, label in PATTERN_LABELS.items():
        print(f"    {label}: {summary[slug]}")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new observer-pattern offender(s):")
        for rel in new:
            for slug in found[rel]:
                print(f"      {rel}  ←  {PATTERN_LABELS[slug]}")
        print(
            "\nFix: bind an @Observable store with @Environment(Type.self) instead of "
            "using legacy environment-object wiring or direct endpoint/service access.\n"
            f"Rule: {RULE_DOC} §1. If this is a legitimately new offender staged for "
            "migration, add its file path to KNOWN_VIOLATIONS with the issue #."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No new observer-pattern regressions beyond the known migration backlog.")
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
    _require_scan_roots_4382(VIEWS_DIR)
    raise SystemExit(main())
