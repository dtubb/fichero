#!/usr/bin/env python3
"""Observer-pattern guardrail for SwiftUI Views.

Rule (see docs/architecture/swiftui/observable_data_layer.md §1):

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
RULE_DOC = "docs/architecture/swiftui/observable_data_layer.md"

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

# Keys are repo-relative file paths. The value is a short backlog note.
KNOWN_VIOLATIONS: dict[str, str] = dict.fromkeys(
    [
        "fichero/fichero/Views/AIProviders/AIModelCatalog.swift",
        "fichero/fichero/Views/AIProviders/AIModelSelectionView.swift",
        "fichero/fichero/Views/AIProviders/AIProviderAddModelsSheet.swift",
        "fichero/fichero/Views/AIProviders/AddProviderSheet.swift",
        "fichero/fichero/Views/AIProviders/ProvidersSettingsSheet.swift",
        "fichero/fichero/Views/AIProviders/ProvidersView+ProviderDetailView.swift",
        "fichero/fichero/Views/AIProviders/ProvidersView.swift",
        "fichero/fichero/Views/Activity/ActivityDetailView.swift",
        "fichero/fichero/Views/Activity/ActivityLogView.swift",
        "fichero/fichero/Views/Activity/ActivityProgressView.swift",
        "fichero/fichero/Views/Activity/ActivityViewHelpers.swift",
        "fichero/fichero/Views/Agents/AgentConfigurationView.swift",
        "fichero/fichero/Views/Agents/AgentSettingsView.swift",
        "fichero/fichero/Views/Automation/ScheduleCreationSheet.swift",
        "fichero/fichero/Views/Automation/ScheduleDetailView.swift",
        "fichero/fichero/Views/Automation/ScheduleEditorView.swift",
        "fichero/fichero/Views/Automation/TriggerCreationSheet.swift",
        "fichero/fichero/Views/Automation/TriggerDetailView.swift",
        "fichero/fichero/Views/Automation/TriggerEditorView.swift",
        "fichero/fichero/Views/Chat/ChatInspector.swift",
        "fichero/fichero/Views/Chat/ChatView.swift",
        "fichero/fichero/Views/Chat/ComparisonDetailView+Actions.swift",
        "fichero/fichero/Views/Chat/ComparisonDetailView.swift",
        "fichero/fichero/Views/Components/BackendConnectionView.swift",
        "fichero/fichero/Views/Components/LibraryImageView.swift",
        "fichero/fichero/Views/ContentView+Actions.swift",
        "fichero/fichero/Views/ContentView+Navigation.swift",
        "fichero/fichero/Views/ContentView+ViewBuilders.swift",
        "fichero/fichero/Views/ContentView.swift",
        "fichero/fichero/Views/ContentViewModifiers.swift",
        "fichero/fichero/Views/DocumentTabView.swift",
        "fichero/fichero/Views/Integrations/IntegrationsView.swift",
        "fichero/fichero/Views/KnowledgeGraph/EntityDigestView.swift",
        "fichero/fichero/Views/KnowledgeGraph/KGMapView.swift",
        "fichero/fichero/Views/KnowledgeGraph/KGTimelineView.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ClaimReviewQueueSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Details.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ContradictionTriageSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EditClaimSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView+Audit.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView+Biography.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView+Metadata.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityMergeSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntitySourceGroupsView.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntitySplitSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ForceDirectedGraphView.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/HeuristicReviewSheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/NewEntitySheet.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser+Detail.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser+List.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser+Toolbar.swift",
        "fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser.swift",
        "fichero/fichero/Views/Library/ArtifactEntityViews.swift",
        "fichero/fichero/Views/Library/DisplayAttributesStrip.swift",
        "fichero/fichero/Views/Library/DocumentCanvas.swift",
        "fichero/fichero/Views/Library/DocumentInspector/AttributedTextEditor.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntityKindRow.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Previews.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab+Bibliography.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab+Citations.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab+Prototype.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab+RelatedClaims.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab+Workflow.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorInfoTab.swift",
        "fichero/fichero/Views/Library/DocumentInspector/SourceOutlineView.swift",
        "fichero/fichero/Views/Library/DocumentInspector.swift",
        "fichero/fichero/Views/Library/DocumentInspectorContentV2.swift",
        "fichero/fichero/Views/Library/DocumentKGSurface.swift",
        "fichero/fichero/Views/Library/ImageEditor/ImageEditorView.swift",
        "fichero/fichero/Views/Library/LibraryToolbarState.swift",
        "fichero/fichero/Views/Library/LibraryView.swift",
        "fichero/fichero/Views/Library/NodeClassPicker.swift",
        "fichero/fichero/Views/Library/PDFLoupeOverlay.swift",
        "fichero/fichero/Views/Library/PDFPageView.swift",
        "fichero/fichero/Views/Library/PDFThumbnailView.swift",
        "fichero/fichero/Views/Library/PageContentPane.swift",
        "fichero/fichero/Views/Library/QuickLookComponents.swift",
        "fichero/fichero/Views/Library/WorkspaceItemPicker.swift",
        "fichero/fichero/Views/MCPServers/AddMCPServerSheet.swift",
        "fichero/fichero/Views/MCPServers/MCPServerDetailView.swift",
        "fichero/fichero/Views/MCPServers/MCPServersView.swift",
        "fichero/fichero/Views/MCPServers/MCPToolsCatalogView.swift",
        "fichero/fichero/Views/Menu/FileMenuCommands.swift",
        "fichero/fichero/Views/Menu/ViewMenuCommands.swift",
        "fichero/fichero/Views/MindPalace/SpatialScene3D.swift",
        "fichero/fichero/Views/ModelComparison/ModelComparisonView.swift",
        "fichero/fichero/Views/ModelComparison/NodeComparisonSheet.swift",
        "fichero/fichero/Views/Onboarding/FirstRunWindow.swift",
        "fichero/fichero/Views/Research/ResearchBrowserPane.swift",
        "fichero/fichero/Views/Research/ResearchChatPane.swift",
        "fichero/fichero/Views/Research/ResearchProjectListView.swift",
        "fichero/fichero/Views/Search/SearchView.swift",
        "fichero/fichero/Views/Settings/AISettingsView.swift",
        "fichero/fichero/Views/Settings/BackendSettingsView.swift",
        "fichero/fichero/Views/Settings/LocalModelsSettingsView.swift",
        "fichero/fichero/Views/Settings/SettingsView.swift",
        # Settings sections exposed by the QR-pairing / sharing work — staged
        # @EnvironmentObject → @Environment(@Observable) migration (#2378).
        "fichero/fichero/Views/Settings/AISettingsView+Tabs.swift",
        "fichero/fichero/Views/Settings/AuditHistoryView.swift",
        "fichero/fichero/Views/Settings/BackupsView.swift",
        "fichero/fichero/Views/Settings/CaptureSettingsView.swift",
        "fichero/fichero/Views/Settings/EngineSettingsView.swift",
        "fichero/fichero/Views/Settings/ShareSettingsView.swift",
        "fichero/fichero/Views/Settings/UsersSettingsView.swift",
        "fichero/fichero/Views/Sheets/DocumentPickerSheet.swift",
        "fichero/fichero/Views/Sheets/WorkflowPickerSheet.swift",
        "fichero/fichero/Views/Sidebar/Components/SidebarObservers.swift",
        "fichero/fichero/Views/Sidebar/SidebarView.swift",
        "fichero/fichero/Views/Workflow/ChainEditorView.swift",
        "fichero/fichero/Views/Library/AnnotationsInspectorPane.swift",
        "fichero/fichero/Views/Library/ArtifactsInspectorPane.swift",
        "fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Interpretations.swift",
        "fichero/fichero/Views/Menu/FocusedCommandButtons.swift",
        "fichero/fichero/Views/Notes/NotesInspectorPane.swift",
        "fichero/fichero/Views/Workflow/NodeConfigs/ExtractEntitiesNodeConfig.swift",
        "fichero/fichero/Views/Workflow/NodeConfigs/SearchNodeConfig.swift",
        "fichero/fichero/Views/Workflow/NodePopover.swift",
        "fichero/fichero/Views/Workflow/PromptPreviewPanel.swift",
        "fichero/fichero/Views/Workflow/WorkflowCanvasView.swift",
        "fichero/fichero/Views/Workflow/WorkflowEditor.swift",
        "fichero/fichero/Views/Workflow/WorkflowInspector.swift",
        "fichero/fichero/Views/Workflow/WorkflowLibraryView.swift",
        "fichero/fichero/Views/Workflow/WorkflowRunProviderCache.swift",
    ],
    "#1851/#1875 baseline",
)


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
