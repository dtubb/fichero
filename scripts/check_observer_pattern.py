#!/usr/bin/env python3
"""Observer-pattern guardrail for SwiftUI Views.

Rule (see docs/contributor/architecture/fichero/observable_data_layer.md §1):

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
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "docs/contributor/architecture/fichero/observable_data_layer.md"

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

# Post-#2960 baseline. The @Observable foundation flip (#2960/#1863) cleared
# every @EnvironmentObject/.environmentObject/@StateObject-service/ObservableObject
# offender. These remaining entries are UNRELATED anti-patterns still on the
# backlog: direct `LibraryManager.shared.globalLibrary` reads, `client.api.`
# access, and the two views that read the kept-ObservableObject FeatureManager
# via @EnvironmentObject (FeatureManager stays ObservableObject — it is backed
# by @AppStorage, which @Observable does not track).
KNOWN_VIOLATIONS: dict[str, str] = dict.fromkeys(
    [
        "fichero/fichero/Views/Chat/ModelComparison/ComparisonDetailView+Actions.swift",
        "fichero/fichero/Views/Shell/ContentView/ContentView+Actions.swift",
        "fichero/fichero/Views/Shell/ContentView/ContentView.swift",
        "fichero/fichero/Views/Inspector/Artifacts/EntityDigestView.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/KGMapView.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/KGTimelineView.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Claim/ClaimReviewQueueSheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Claim/ContradictionTriageSheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Audit.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Biography.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Metadata.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntitySourceGroupsView.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Claim/HeuristicReviewSheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/Entity/NewEntitySheet.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Detail.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+List.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Toolbar.swift",
        "fichero/fichero/Views/Library/ViewModes/Graph/Ontology/OntologyBrowser.swift",
        "fichero/fichero/Views/Inspector/Document/DocumentInspector.swift",
        "fichero/fichero/Views/Inspector/Document/Knowledge/DocumentInspectorArtifactsTab+EntityKindRow.swift",
        "fichero/fichero/Views/Inspector/Document/Notes/DocumentInspectorArtifactsTab+Interpretations.swift",
        "fichero/fichero/Views/Inspector/Document/Source/Info/DocumentInspectorInfoTab+Bibliography.swift",
        "fichero/fichero/Views/Inspector/Document/Source/Info/DocumentInspectorInfoTab+Citations.swift",
        "fichero/fichero/Views/Inspector/Document/Source/Info/DocumentInspectorInfoTab+Prototype.swift",
        "fichero/fichero/Views/Inspector/Document/Source/Info/DocumentInspectorInfoTab+RelatedClaims.swift",
        "fichero/fichero/Views/Inspector/Document/Source/Info/DocumentInspectorInfoTab+Workflow.swift",
        "fichero/fichero/Views/Components/NodeClassPicker.swift",
        "fichero/fichero/Views/Shell/Menu/FocusedCommandButtons.swift",
        "fichero/fichero/Views/Settings/AI/LocalModelsSettingsView.swift",
        "fichero/fichero/Views/Sidebar/Modes/SidebarModeBar.swift",
        "fichero/fichero/Views/Shell/DocumentTabView.swift",
        "fichero/fichero/Views/Library/ViewModes/Canvas/3D/Legacy/SpaceSceneView.swift",
        "fichero/fichero/Views/Library/ViewModes/Canvas/2D/Legacy/SpatialNodeThumbnail.swift",
        "fichero/fichero/Views/Workflow/Nodes/NodeConfigs/ExtractEntitiesNodeConfig.swift",
        "fichero/fichero/Views/Workflow/Nodes/NodePopover.swift",
        "fichero/fichero/Views/Workflow/Canvas/WorkflowCanvasView.swift",
        "fichero/fichero/Views/Workflow/Editor/WorkflowEditor.swift",
        "fichero/fichero/Views/Workflow/Nodes/WorkflowNodeView.swift",
    ],
    "post-#2960 residual (globalLibrary / client.api. / FeatureManager)",
)

# Stated plainly, with an owner — an allowlist entry that only makes red go away is
# not acceptable. The Settings panes read FeatureManager via @EnvironmentObject
# (injected by the Settings scene) INSTEAD of grabbing FeatureManager.shared, which
# is the improvement; they cannot use @Environment because:
KNOWN_VIOLATIONS["fichero/fichero/Views/Settings/SettingsView.swift"] = (
    "FeatureManager is @AppStorage-backed (~50 flags); @AppStorage requires "
    "ObservableObject, so @Observable is not available here (the @Observable macro "
    "rewrites stored properties into computed ones, and a property wrapper cannot be "
    "applied to a computed property — it fails to build). The Settings scene injects "
    "it and the panes bind @EnvironmentObject rather than reaching for .shared. "
    "Tracked for conversion in #3743."
)
KNOWN_VIOLATIONS.update({
    "fichero/fichero/Views/Shell/ContentView/ContentViewModifiers.swift": (
        "FeatureManager remains @AppStorage-backed ObservableObject; the app root injects it "
        "and this modifier binds it with @EnvironmentObject rather than reading .shared. "
        "Tracked for conversion in #3743."
    ),
    "fichero/fichero/Views/Library/Workspace/LibraryWorkspaceRoot.swift": (
        "FeatureManager remains @AppStorage-backed ObservableObject; the app root injects it "
        "and this workspace root binds it with @EnvironmentObject rather than reading .shared. "
        "Tracked for conversion in #3743."
    ),
})


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

    if re.search(
        r"@StateObject[^\n=]*=\s*[A-Za-z_][A-Za-z0-9_]*Service(?:Generated)?\s*\(",
        src,
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
    for path in sorted(VIEWS_DIR.rglob("*.swift")):
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


if __name__ == "__main__":
    raise SystemExit(main())
