#!/usr/bin/env python3
"""Swift file guard — a Swift file is named for the one primary type it declares.

spec: code-organization — `code-org.naming.swift-file-is-type` (and the naming rules for views and platform suffixes).

Over `fichero/fichero/**/*.swift` (not `fichero-api-client`, not generated files), with comments and strings stripped:

  1. one-type      more than ONE top-level `struct|class|enum|actor|protocol` that is not `private`/`fileprivate`.
                   Not counted: `*Preview` types (`#Preview` is a macro, not a type); a `<Service>Types.swift` or
                   `<X>WireModels.swift` under `Services/` (the owner keeps the wire bundles, ruling 2 of 2026-11-14).
                   A `Type+Topic.swift` file may carry extra types only when they are `private`.
  2. file-name     a file with no `+` has a stem equal to one of its top-level type names (or a type name that starts with
                   the stem: `FooView.swift` holding `FooView` and `FooViewModel`). A `Type+Topic.swift` file contains
                   `extension Type`.
  3. view-shape    a top-level type conforming to `View` ends in a shape word (SHAPE_WORDS), and sits under `Views/`
                   (or `App/Menus/`, or is named `*Scene`/`*Window` under `App/`).
  4. platform      a file stem or type name ending `iOS`, `macOS` or `iOSOnly` is spelled `IOS` / `MacOS`
                   (owner ruling 4 of 2026-11-14).

`KNOWN_VIOLATIONS` maps each file with findings to its finding count at baseline; the count may only fall. A file above its
count, or a new file with findings, exits 1. Exit 2 is BLIND (fewer than FLOOR Swift files scanned).

Usage:
    python3 scripts/check_swift_one_type_per_file.py
    python3 scripts/check_swift_one_type_per_file.py --list        every finding, one per line
    python3 scripts/check_swift_one_type_per_file.py --generate    print KNOWN_VIOLATIONS for today's tree
    python3 scripts/check_swift_one_type_per_file.py --self-test   plant each kind of finding in a scratch tree
"""
from __future__ import annotations

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from _check_floor import require_scan_floor
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
FLOOR = 400  # 0.5 x the app's Swift files, as the sibling guards

SHAPE_WORDS = (
    "View Pane Sheet Row Bar Button Menu Picker Popover Cell Badge Label Overlay Section Item Field Panel Strip Card Line "
    "Notice Pill Host Content Modifier Stage Screen Page Tab Tabs Toolbar Header Footer Chip Indicator Banner Grid List "
    "Stack Canvas Editor Viewer Inspector Reader Sidebar Window Scene Renderer Commands"
).split()
PLATFORM_BAD = ("iOSOnly", "macOS", "iOS")  # longest first
PLATFORM_FIX = {"iOSOnly": "IOSOnly", "macOS": "MacOS", "iOS": "IOS"}
WIRE_BUNDLE = re.compile(r"^(?:.+Types|.+WireModels)$")

_KEYWORDS = frozenset({"func", "var", "let", "init", "subscript", "case", "where", "is", "as"})
_DECL = re.compile(
    r"^[ \t]*((?:@[A-Za-z_]\w*(?:\([^)]*\))?[ \t]+|\b(?:public|internal|open|package|final|private|fileprivate|indirect|nonisolated)"
    r"(?:\([a-z]+\))?[ \t]+)*)(struct|class|enum|actor|protocol)[ \t]+([A-Za-z_]\w*)",
    re.MULTILINE,
)
_EXT = re.compile(r"^[ \t]*(?:@\w+[ \t]+)*(?:(?:public|internal|private|fileprivate|package)[ \t]+)?extension[ \t]+([A-Za-z_][\w.]*)", re.MULTILINE)
_ALIAS = re.compile(r"^[ \t]*(?:(?:public|internal|private|fileprivate)[ \t]+)?typealias[ \t]+([A-Za-z_]\w*)", re.MULTILINE)


@dataclass(frozen=True)
class TypeDecl:
    name: str
    kind: str
    private: bool
    is_view: bool


@dataclass
class Facts:
    types: list[TypeDecl]
    extensions: list[str]
    aliases: list[str]


def strip_comments_and_strings(src: str) -> str:
    """The source with comments and string contents blanked (newlines kept, so line shapes survive)."""
    out: list[str] = []
    n = len(src)

    def string_end(i: int, hashes: int, multi: bool) -> int:
        """Index just past the string whose opening quote(s) end at i."""
        close = '"' * (3 if multi else 1) + "#" * hashes
        while i < n:
            c = src[i]
            if src.startswith("\\" + "#" * hashes + "(", i):
                i = paren_end(i + 2 + hashes)
                continue
            if c == "\\" and hashes == 0:
                i += 2
                continue
            if src.startswith(close, i):
                return i + len(close)
            if c == "\n" and not multi:
                return i  # unterminated: stop at the line end
            i += 1
        return n

    def paren_end(i: int) -> int:
        depth = 1
        while i < n and depth:
            c = src[i]
            if c == '"':
                multi = src.startswith('"""', i)
                i = string_end(i + (3 if multi else 1), 0, multi)
                continue
            depth += (c == "(") - (c == ")")
            i += 1
        return i

    i = 0
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append("".join("\n" for ch in src[i:j] if ch == "\n"))
            i = j
        elif c == '"' or (c == "#" and re.match(r'#+"', src[i:i + 40] or "")):
            hashes = 0
            while src[i] == "#":
                hashes, i = hashes + 1, i + 1
            multi = src.startswith('"""', i)
            j = string_end(i + (3 if multi else 1), hashes, multi)
            out.append('""' + "".join("\n" for ch in src[i:j] if ch == "\n"))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _clause_conforms_to_view(code: str, pos: int) -> bool:
    """Whether the declaration whose name ends at `pos` lists `View` among its inherited types."""
    if code[pos:pos + 1] == "<":  # skip the generic parameter list
        depth = 0
        while pos < len(code):
            depth += (code[pos] == "<") - (code[pos] == ">")
            pos += 1
            if depth == 0:
                break
    head = code[pos:code.find("{", pos) if code.find("{", pos) >= 0 else len(code)]
    head = head.split(" where ")[0]
    if ":" not in head:
        return False
    items = [x.strip() for x in head.split(":", 1)[1].split(",")]
    return any(x in ("View", "SwiftUI.View") for x in items)


def analyze(src: str) -> Facts:
    code = strip_comments_and_strings(src)
    # blank everything nested in braces, so only top-level declarations match
    depth, flat = 0, []
    for ch in code:
        if ch == "{":
            depth += 1
            flat.append(ch if depth == 1 else " ")
        elif ch == "}":
            flat.append(ch if depth == 1 else " ")
            depth = max(depth - 1, 0)
        else:
            flat.append(ch if depth == 0 or ch == "\n" else " ")
    top = "".join(flat)
    types = []
    for m in _DECL.finditer(top):
        name = m.group(3)
        if name in _KEYWORDS:
            continue
        mods = m.group(1)
        types.append(TypeDecl(name, m.group(2), bool(re.search(r"\b(?:private|fileprivate)\b(?!\()", mods)),
                              _clause_conforms_to_view(top, m.end())))
    return Facts(types, [m.group(1).split(".")[0] for m in _EXT.finditer(top)], [m.group(1) for m in _ALIAS.finditer(top)])


def is_exempt_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return "fichero-api-client" in rel or name.endswith("Generated.swift") or name.endswith(".generated.swift")


def file_findings(rel: str, facts: Facts) -> list[str]:
    """Findings for one file; `rel` is relative to fichero/fichero. Each is `<rule>: <what to do>`."""
    name = rel.rsplit("/", 1)[-1]
    stem = name[:-len(".swift")]
    out: list[str] = []
    public = list({t.name: t for t in facts.types if not t.private and not t.name.endswith("Preview")}.values())  # an #if pair declares one name twice
    under_services = rel.startswith("Services/")
    wire = under_services and bool(WIRE_BUNDLE.match(stem))
    if len(public) > 1 and not wire:
        out.append(f"one-type: {len(public)} non-private top-level types ({', '.join(t.name for t in public)}): one file per type")
    names = [t.name for t in facts.types] + facts.extensions + facts.aliases
    if "+" in stem:
        base = stem.split("+", 1)[0]
        if base not in facts.extensions and facts.types is not None and (facts.extensions or facts.types):
            out.append(f"file-name: {name} must contain `extension {base}`")
    elif names and not wire and not any(n == stem or n.startswith(stem) for n in names):
        out.append(f"file-name: {name} declares {', '.join(names[:3])}: name the file for its type")
    for t in facts.types:
        if t.is_view:
            if not t.name.endswith(tuple(SHAPE_WORDS)):
                out.append(f"view-shape: View type {t.name} ends in no shape word")
            in_place = (rel.startswith("Views/") or rel.startswith("App/Menus/")
                        or (rel.startswith("App/") and t.name.endswith(("Scene", "Window"))))
            if not in_place:
                out.append(f"view-place: View type {t.name} sits outside Views/ (menus: App/Menus/)")
    bad_stem = [s for s in PLATFORM_BAD if stem.endswith(s)]
    if bad_stem:
        out.append(f"platform: file {name} ends {bad_stem[0]}: spell it {PLATFORM_FIX[bad_stem[0]]}")
    for t in facts.types:
        bad = [s for s in PLATFORM_BAD if t.name.endswith(s)]
        if bad:
            out.append(f"platform: type {t.name} ends {bad[0]}: spell it {PLATFORM_FIX[bad[0]]}")
    return out


def scan(root: Path | None = None) -> tuple[dict[str, list[str]], int]:
    """({relative path: findings}, Swift files scanned)."""
    root = root or SWIFT_ROOT
    found: dict[str, list[str]] = {}
    count = 0
    for path in sorted(scan_rglob(root, "*.swift")):
        rel = path.relative_to(root).as_posix()
        if is_exempt_path(rel):
            continue
        count += 1
        findings = file_findings(rel, analyze(path.read_text(encoding="utf-8", errors="replace")))
        if findings:
            found[rel] = findings
    return found, count


# Baseline of today's tree (`--generate`): file -> findings. The count may only fall.
KNOWN_VIOLATIONS: dict[str, int] = {
    "App/AppState/AppState.swift": 1,
    "App/LibraryWindow+Actions.swift": 1,
    "App/Menus/CanvasMenuCommands.swift": 1,
    "App/Menus/FileMenuCommands.swift": 1,
    "App/Menus/FocusedCommands/DoubtfulWordCommands.swift": 1,
    "App/Menus/FocusedCommands/FocusedCommandButtons+Activity.swift": 6,
    "App/Menus/FocusedCommands/FocusedCommandButtons+CreationActions.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+FocusedValues.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+NavigationKeys.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+SidebarActions.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+Train.swift": 3,
    "App/Menus/FocusedCommands/FocusedCommandButtons+Trash.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+UndoNavigation.swift": 2,
    "App/Menus/FocusedCommands/FocusedCommandButtons+Workflow.swift": 1,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+AutomationVerbs.swift": 3,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+ItemVerbs.swift": 3,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+LineVerbs.swift": 4,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+OpenVerbs.swift": 3,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+ProjectVerbs.swift": 3,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+ProposalVerbs.swift": 3,
    "App/Menus/FocusedCommands/ItemVerbs/FocusedCommandButtons+RunAndChatVerbs.swift": 2,
    "App/Menus/FocusedCommands/RotateImageCommands.swift": 2,
    "App/Menus/FocusedCommands/SegmentMenuCommands.swift": 2,
    "App/Menus/Help/SaveLogsForSupport.swift": 1,
    "App/Menus/ReaderExportCommands.swift": 3,
    "App/Menus/UndoRouting.swift": 1,
    "App/Menus/ViewMenuCommands.swift": 1,
    "App/Menus/ViewMenuLayoutSections.swift": 2,
    "App/Menus/ViewMenuPaneSections.swift": 4,
    "App/Menus/ViewMenuSortAndModeSections.swift": 2,
    "App/Menus/WorkspacesMenuBody.swift": 1,
    "App/RenderDiagnostics.swift": 1,
    "App/ViewModeTypes.swift": 2,
    "App/ViewSettings.swift": 1,
    "FicheroApp.swift": 2,
    "FicheroApp_iOS.swift": 6,
    "Intents/FicheroActionIntents.swift": 2,
    "Intents/FicheroAppEntities.swift": 2,
    "Intents/FicheroUIVerbIntents.swift": 2,
    "Intents/UIVerbs.swift": 1,
    "Models/ActivityErrorLedger.swift": 1,
    "Models/ActivityLogFilter.swift": 1,
    "Models/ActivityRun.swift": 1,
    "Models/ActivityStore+Archive.swift": 1,
    "Models/AlwaysThereProject.swift": 1,
    "Models/AppNavigationHistory.swift": 1,
    "Models/AppleAvailabilityStore.swift": 1,
    "Models/Artifact.swift": 1,
    "Models/ArtifactEntityStore.swift": 1,
    "Models/AuditedAction.swift": 1,
    "Models/BackendActivityEvent.swift": 1,
    "Models/BulkDelete.swift": 1,
    "Models/CanvasItemStore.swift": 1,
    "Models/CanvasLayoutStore.swift": 1,
    "Models/ClaimPatchFields.swift": 1,
    "Models/ComparisonTypes.swift": 2,
    "Models/ConversionStatusStore.swift": 1,
    "Models/Document.swift": 1,
    "Models/DocumentStore.swift": 1,
    "Models/DocumentTypes.swift": 2,
    "Models/EntityStore.swift": 1,
    "Models/ErrorModel.swift": 1,
    "Models/FicheroDocument.swift": 1,
    "Models/FoundDocumentsStore.swift": 1,
    "Models/GeneratedTypeExtensions.swift": 1,
    "Models/HostGoneRow.swift": 1,
    "Models/IIIFImportStore.swift": 1,
    "Models/InspectorEditorial.swift": 1,
    "Models/InspectorLinks.swift": 1,
    "Models/InspectorRights.swift": 1,
    "Models/ItemTypeRegistry.swift": 1,
    "Models/ItemsPane.swift": 1,
    "Models/KnowledgeRowCountsStore.swift": 1,
    "Models/KnowledgeSettingsStore.swift": 1,
    "Models/KnownLibraryRegistryStore.swift": 1,
    "Models/LayoutMode.swift": 1,
    "Models/LibraryAccessGrant.swift": 1,
    "Models/LibraryManager.swift": 1,
    "Models/LibraryRootDropRouting.swift": 1,
    "Models/LocalInferenceStore.swift": 1,
    "Models/LocalModelsStore.swift": 1,
    "Models/MCPServer.swift": 1,
    "Models/MobileCaptureQueue+Enqueueing.swift": 1,
    "Models/MobileCaptureQueue+Persistence.swift": 1,
    "Models/MobileCaptureQueue+Query.swift": 1,
    "Models/MobileCaptureQueue+Removal.swift": 1,
    "Models/MobileCaptureQueue+Uploading.swift": 1,
    "Models/MobileCaptureQueue.swift": 1,
    "Models/NoteStaleResolution.swift": 1,
    "Models/OCRGeometry.swift": 1,
    "Models/ObservableDomainStore.swift": 1,
    "Models/OpeningSelection.swift": 1,
    "Models/OriginalsStore.swift": 1,
    "Models/PairInvitesStore.swift": 1,
    "Models/PairedHostEndpoints.swift": 1,
    "Models/PairedMachine.swift": 1,
    "Models/PaneList.swift": 2,
    "Models/PaneListModel.swift": 1,
    "Models/Platform/PlatformAliases.swift": 6,
    "Models/PrepareOperationRows.swift": 1,
    "Models/PreviewImageGeometry.swift": 1,
    "Models/ProjectTransferStore.swift": 1,
    "Models/ReaderLines.swift": 1,
    "Models/ReaderSearchMatchState.swift": 1,
    "Models/ReadingChoice.swift": 1,
    "Models/ReadingDisagreement.swift": 1,
    "Models/ReadingOrderChoice.swift": 1,
    "Models/ReadyReads.swift": 1,
    "Models/ReadySections.swift": 1,
    "Models/RecipeSetupAnswers.swift": 1,
    "Models/RegionSelection.swift": 1,
    "Models/RenditionChainStrip.swift": 2,
    "Models/ResearchModels.swift": 2,
    "Models/ReviewAcceptAll.swift": 1,
    "Models/Run.swift": 1,
    "Models/SearchResult.swift": 1,
    "Models/SearchStore.swift": 1,
    "Models/Segment.swift": 1,
    "Models/SegmentBulkEdit.swift": 1,
    "Models/SegmentEdit+Tools.swift": 1,
    "Models/SegmentEdit.swift": 1,
    "Models/SegmentEditRunner.swift": 1,
    "Models/SegmentHistory.swift": 1,
    "Models/SegmentMover.swift": 1,
    "Models/SegmentShapes+Draw.swift": 1,
    "Models/SegmentShapes.swift": 1,
    "Models/SegmentsGather.swift": 1,
    "Models/SegmentsPane.swift": 1,
    "Models/SessionStore.swift": 1,
    "Models/SetupFlow.swift": 1,
    "Models/SetupStageTryFigures.swift": 2,
    "Models/SetupStageTryStore.swift": 1,
    "Models/SidebarChatTypes.swift": 2,
    "Models/SidebarColumnState.swift": 1,
    "Models/SidebarItem.swift": 1,
    "Models/SidebarSearchTypes.swift": 2,
    "Models/SidebarState.swift": 1,
    "Models/SidebarViewTypes.swift": 2,
    "Models/SourceDirection.swift": 1,
    "Models/SourcePaneImageActions.swift": 1,
    "Models/SpatialModels+Links.swift": 2,
    "Models/SpatialModels.swift": 2,
    "Models/StageCandidate.swift": 1,
    "Models/StageShowcase.swift": 1,
    "Models/StatsResponse.swift": 1,
    "Models/StepOutputState.swift": 1,
    "Models/SuggestionRows.swift": 2,
    "Models/TrainedModelsStore.swift": 1,
    "Models/TrashStore.swift": 1,
    "Models/TryLabels.swift": 2,
    "Models/UndoableChange.swift": 1,
    "Models/UsersStore.swift": 1,
    "Models/ViewContexts.swift": 2,
    "Models/WindowState+SegmentTools.swift": 1,
    "Models/WindowSteps.swift": 1,
    "Models/WorkflowChain.swift": 1,
    "Models/WorkflowExecutionStore.swift": 1,
    "Models/WorkflowResponseTypes.swift": 2,
    "Models/WorkflowRunTargetResolver.swift": 1,
    "Models/WorkflowStore.swift": 1,
    "Models/WorkflowSuggestionPolicy.swift": 1,
    "Models/WorkflowSupportTypes.swift": 2,
    "Models/WorkflowToolTypes.swift": 2,
    "Models/WorkflowTypes.swift": 2,
    "Models/WorkingPassChoice.swift": 1,
    "Services/APIClient+Types.swift": 1,
    "Services/AccessError.swift": 1,
    "Services/ActionInvokeService.swift": 2,
    "Services/ActionsService.swift": 1,
    "Services/ActivityService.swift": 1,
    "Services/AddressChoiceModel.swift": 1,
    "Services/AnnotationService.swift": 1,
    "Services/AppleScriptCommands.swift": 2,
    "Services/AppleScriptRunCommands.swift": 2,
    "Services/AppleScriptSupport.swift": 2,
    "Services/AppleScriptUIVerbs.swift": 2,
    "Services/ArtifactService.swift": 1,
    "Services/Auth/OwnerKeyStore.swift": 1,
    "Services/Auth/OwnerSignIn.swift": 2,
    "Services/Auth/OwnerSignInCoordinator.swift": 1,
    "Services/AutomationAPIService.swift": 1,
    "Services/AutomationServiceMappers.swift": 1,
    "Services/BatchService.swift": 1,
    "Services/BookmarkService.swift": 1,
    "Services/ChainService.swift": 1,
    "Services/ChangeStreamTransport.swift": 1,
    "Services/ChatService.swift": 1,
    "Services/CheckService.swift": 1,
    "Services/Connectivity/BonjourDiscoveryService.swift": 1,
    "Services/Connectivity/SyncedHostAsk.swift": 1,
    "Services/ConversationService.swift": 1,
    "Services/DebugScriptVerbs.swift": 1,
    "Services/DocumentService+Dataset.swift": 1,
    "Services/DocumentService.swift": 1,
    "Services/EmbeddedBackendService+Spawn.swift": 1,
    "Services/EmbeddedBackendService.swift": 1,
    "Services/EngineConfig.swift": 1,
    "Services/EngineHostSwitch.swift": 1,
    "Services/EngineReadinessProbe.swift": 1,
    "Services/EngineRestartPolicy.swift": 1,
    "Services/EngineSession.swift": 1,
    "Services/EngineSocketConflict.swift": 1,
    "Services/EntityService.swift": 1,
    "Services/FicheroUICapture.swift": 1,
    "Services/FolderAccessManager.swift": 1,
    "Services/HostKeyProbe.swift": 1,
    "Services/ImageCleanupBatchService.swift": 1,
    "Services/ImageEditingService.swift": 1,
    "Services/ImportService+Conversions.swift": 1,
    "Services/ImportService.swift": 1,
    "Services/LibraryChangeStream.swift": 1,
    "Services/LivePairingHost.swift": 1,
    "Services/LocationService.swift": 1,
    "Services/MCPService.swift": 1,
    "Services/ModelService.swift": 1,
    "Services/NoteService.swift": 1,
    "Services/PairingRestoreDiagnostics.swift": 1,
    "Services/PerformanceService.swift": 1,
    "Services/ProviderAPIService.swift": 1,
    "Services/ReadingOrderService.swift": 1,
    "Services/RemoteAccessConfig.swift": 1,
    "Services/RemoteClientPairing.swift": 1,
    "Services/RemoteClientPairingFlow+Exchange.swift": 1,
    "Services/RemoteClientPairingFlow.swift": 1,
    "Services/RenditionService.swift": 1,
    "Services/RunComparison.swift": 1,
    "Services/SandboxAccessService.swift": 1,
    "Services/SavedSearchService.swift": 1,
    "Services/SearchService.swift": 1,
    "Services/SegmentService.swift": 1,
    "Services/SpatialLibraryProjector.swift": 1,
    "Services/StorageResource/EngineWebViewSchemeHandler.swift": 1,
    "Services/StorageResource/StorageResourceLoader.swift": 1,
    "Services/StorageService.swift": 1,
    "Services/WindowDescription.swift": 1,
    "Services/WorkflowExecutionService.swift": 1,
    "Services/WorkflowRunResponse.swift": 1,
    "Views/About/AboutPreview.swift": 2,
    "Views/About/AboutView.swift": 1,
    "Views/Activity/ActivityPopoverRunView.swift": 2,
    "Views/Activity/ActivityPopoverSummary.swift": 1,
    "Views/Activity/ActivityViewHelpers.swift": 1,
    "Views/Activity/Comparison/RunComparisonRows.swift": 2,
    "Views/Activity/Comparison/RunComparisonView.swift": 1,
    "Views/Activity/Detail/ActivityDetails+RunStages.swift": 1,
    "Views/Activity/Detail/ActivityDetailsCapStop.swift": 1,
    "Views/Activity/Detail/ActivityDetailsDisclosure.swift": 1,
    "Views/Activity/Detail/ActivityDetailsLog.swift": 3,
    "Views/Activity/Detail/ActivityDetailsSections.swift": 9,
    "Views/Activity/Detail/ActivityDetailsStageCards.swift": 1,
    "Views/Activity/Monitor/ActivityMonitorModel.swift": 1,
    "Views/Activity/Monitor/ActivityMonitorPhase.swift": 1,
    "Views/Activity/Pane/ActivityInspectorSection.swift": 1,
    "Views/Activity/Pane/ActivityPaneVerbs.swift": 2,
    "Views/Activity/Pane/ActivityPaneView+Actions.swift": 1,
    "Views/Activity/Pane/ActivityPaneView+Table.swift": 1,
    "Views/Activity/Pane/ShowInActivityMenuItem.swift": 1,
    "Views/Activity/ProjectRunStrip.swift": 1,
    "Views/Activity/RunControls.swift": 1,
    "Views/Activity/Trace/RunTraceModel.swift": 1,
    "Views/Activity/Trace/RunTraceStatusStyle.swift": 2,
    "Views/Activity/Trace/RunTraceStepStatus.swift": 1,
    "Views/Activity/Trace/RunTraceView.swift": 1,
    "Views/Capture/CaptureInlineRowIOS.swift": 1,
    "Views/Capture/MobileCapturePickers.swift": 2,
    "Views/Capture/MobileCaptureQueueView.swift": 1,
    "Views/Chat/ChatStatusViews.swift": 2,
    "Views/Chat/ChatView+Extensions.swift": 1,
    "Views/Chat/ChatView.swift": 1,
    "Views/Chat/ChatViewToolbar.swift": 1,
    "Views/Chat/MessageCard.swift": 2,
    "Views/Chat/ModelComparison/ComparisonDetailView+Models.swift": 2,
    "Views/Chat/ModelComparison/ComparisonResultView.swift": 1,
    "Views/Components/BackendRootGate.swift": 1,
    "Views/Components/DragPreviewLabel.swift": 2,
    "Views/Components/FicheroWebView.swift": 1,
    "Views/Components/LibraryImageView.swift": 1,
    "Views/Components/MarkdownText.swift": 2,
    "Views/Components/Menus/RevealOriginalMenuItem.swift": 1,
    "Views/Components/Menus/RunWorkflowSubmenuItems.swift": 1,
    "Views/Components/MiniToolbar.swift": 2,
    "Views/Components/MiniToolbarOverflow.swift": 2,
    "Views/Components/NodeClassPicker.swift": 1,
    "Views/Components/PaneFilterBar.swift": 1,
    "Views/Components/PaneFilterField.swift": 1,
    "Views/Components/ReadingOrderList.swift": 1,
    "Views/Components/RubberBand.swift": 1,
    "Views/Components/SkeletonPlaceholder.swift": 1,
    "Views/Components/SourceDirectionMenu.swift": 1,
    "Views/Components/SplittablePane.swift": 1,
    "Views/Connect/ConnectDiscoveredMacsSectionIOS.swift": 1,
    "Views/Connect/ConnectPairingEntryIOS.swift": 2,
    "Views/Connect/ConnectPairingIOS.swift": 1,
    "Views/Connect/ConnectQRScannerIOS.swift": 1,
    "Views/Connect/HostTrustAlert.swift": 1,
    "Views/Inspector/Artifacts/ArtifactEntityViews.swift": 2,
    "Views/Inspector/Artifacts/ArtifactListView.swift": 1,
    "Views/Inspector/Artifacts/ArtifactPanel+Regions.swift": 1,
    "Views/Inspector/Artifacts/ArtifactRunGrouping.swift": 1,
    "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift": 1,
    "Views/Inspector/Document/DocumentInspector.swift": 1,
    "Views/Inspector/FocusedDocument.swift": 1,
    "Views/Inspector/InspectorPresenter.swift": 2,
    "Views/Inspector/Knowledge/Citations/CitationExportButton.swift": 1,
    "Views/Inspector/Knowledge/Citations/CitationsInspectorPane.swift": 1,
    "Views/Inspector/Knowledge/Citations/FocusedCitation.swift": 1,
    "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+SupportTypes.swift": 2,
    "Views/Inspector/Knowledge/EntityDigestView.swift": 1,
    "Views/Inspector/Knowledge/EntityKindBlock.swift": 1,
    "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+SupportingTypes.swift": 1,
    "Views/Inspector/Knowledge/KnowledgeGraphModels.swift": 2,
    "Views/Inspector/Knowledge/KnowledgeGraphPreviews.swift": 3,
    "Views/Inspector/Knowledge/KnowledgeGraphSupport.swift": 3,
    "Views/Inspector/Model/ModelNodeInspector.swift": 2,
    "Views/Inspector/Notes/Annotations/AnnotationDetailView.swift": 1,
    "Views/Inspector/Notes/Annotations/AnnotationListView.swift": 1,
    "Views/Inspector/Notes/Annotations/AnnotationsInspectorPane.swift": 1,
    "Views/Inspector/Notes/FocusedNote.swift": 1,
    "Views/Inspector/Notes/NotesInspectorPane.swift": 1,
    "Views/Inspector/Source/DocumentInspectorContentV2.swift": 1,
    "Views/Inspector/Source/Folder/FoundDocumentsSection.swift": 1,
    "Views/Inspector/Source/Folder/SyncedFolderSection.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Attributes.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Bibliography.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+BibliographyRow.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Citations.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Language.swift": 2,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Prototype.swift": 2,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+ReferenceEditSheet.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+RelatedClaims.swift": 1,
    "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Workflow.swift": 1,
    "Views/Inspector/Source/Info/InspectorAttributeVisibility.swift": 1,
    "Views/Inspector/Source/Info/OriginWords.swift": 1,
    "Views/Inspector/Source/InspectorReadingEditor.swift": 1,
    "Views/Inspector/Source/InspectorSegmentGroups.swift": 4,
    "Views/Inspector/Source/InspectorStatementEditors.swift": 2,
    "Views/Inspector/Source/Sections/InspectorMakingSection.swift": 1,
    "Views/Inspector/Source/Sections/InspectorTextSection.swift": 1,
    "Views/Inspector/Source/Sections/ReadingAgreementInspectorSection.swift": 2,
    "Views/Inspector/Source/Sections/WhatHasBeenRunSection.swift": 1,
    "Views/Inspector/Source/SourceOutlineView.swift": 1,
    "Views/Inspector/Source/SourceSectionView.swift": 1,
    "Views/Inspector/Source/Tries/InspectorTriesSection.swift": 1,
    "Views/Inspector/SourceProvenancePopover.swift": 2,
    "Views/Inspector/SourceSnippet.swift": 2,
    "Views/Library/Actions/ActionDetailView.swift": 1,
    "Views/Library/Actions/ActionLibraryView.swift": 1,
    "Views/Library/Actions/ActionPickerView.swift": 1,
    "Views/Library/BlankProposalsLine.swift": 1,
    "Views/Library/EntityThumbnailView.swift": 1,
    "Views/Library/HiddenPagesLine.swift": 1,
    "Views/Library/IIIFImport.swift": 1,
    "Views/Library/LibraryActivityIndicator.swift": 2,
    "Views/Library/LibraryEmptyReason.swift": 1,
    "Views/Library/LibraryPickerMenuIOS.swift": 1,
    "Views/Library/LibraryRowAttributes.swift": 1,
    "Views/Library/LibraryThumbnailComponents.swift": 3,
    "Views/Library/LibraryThumbnailViews.swift": 1,
    "Views/Library/LibraryView+EmptyFolder.swift": 1,
    "Views/Library/LibraryView+InlineEditing.swift": 1,
    "Views/Library/LibraryView+Sorting.swift": 1,
    "Views/Library/LibraryView.swift": 1,
    "Views/Library/LibraryViewComponents.swift": 2,
    "Views/Library/LibraryViewFocusedValues.swift": 2,
    "Views/Library/LocateOriginals.swift": 2,
    "Views/Library/ProjectTransferSheet.swift": 1,
    "Views/Library/ProposedDocumentsInItems.swift": 2,
    "Views/Library/Search/SearchFieldOptionsMenu.swift": 1,
    "Views/Library/Search/SearchMatchSourceChips.swift": 2,
    "Views/Library/Search/ToolbarSearchField.swift": 1,
    "Views/Library/ShowThroughOnlyLine.swift": 1,
    "Views/Library/SyncedHostAskSheet.swift": 1,
    "Views/Library/TextPreviewThumbnail.swift": 3,
    "Views/Library/TrashPane.swift": 1,
    "Views/Library/ViewModes/Canvas/2D/Legacy/Spatial2DCanvasGestures.swift": 1,
    "Views/Library/ViewModes/Canvas/2D/Legacy/Spatial2DCanvasItems.swift": 1,
    "Views/Library/ViewModes/Canvas/2D/Legacy/SpatialNodeThumbnail.swift": 1,
    "Views/Library/ViewModes/Canvas/2D/Legacy/SpatialView.swift": 1,
    "Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift": 1,
    "Views/Library/ViewModes/Canvas/CanvasArrangePicker.swift": 1,
    "Views/Library/ViewModes/Canvas/CanvasColourPicker.swift": 1,
    "Views/Library/ViewModes/Canvas/CanvasContextMenu.swift": 1,
    "Views/Library/ViewModes/Canvas/CanvasScrollPan.swift": 1,
    "Views/Library/ViewModes/Canvas/CanvasTouchPan.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasArrangement.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasDropOutcome.swift": 2,
    "Views/Library/ViewModes/Canvas/Engine/CanvasGridPlacement.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasGroupNesting.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasInteractionController.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasSceneDiff.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/CanvasSceneState.swift": 1,
    "Views/Library/ViewModes/Canvas/Engine/Cards/CanvasCardFace.swift": 1,
    "Views/Library/ViewModes/Dataset/DatasetFilterCluster.swift": 2,
    "Views/Library/ViewModes/Dataset/DatasetModeStore.swift": 1,
    "Views/Library/ViewModes/Dataset/DatasetModeView.swift": 1,
    "Views/Library/ViewModes/Dataset/DatasetPreviewFixtures.swift": 1,
    "Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift": 1,
    "Views/Library/ViewModes/Graph/KGTemporalSpatial.swift": 2,
    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCardView+Navigation.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCardView.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Claim/EditClaimSheet.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Claim/HeuristicReviewSheet.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Notes.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntityReconciliationSheet.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Entity/EntityRowView.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/Entity/WikidataEnrichmentSheet.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/GraphModel.swift": 2,
    "Views/Library/ViewModes/Graph/Ontology/SpeakerComparisonView+Preview.swift": 1,
    "Views/Library/ViewModes/Graph/Ontology/SpeakerComparisonView.swift": 1,
    "Views/Library/ViewModes/Icon/LibraryMarquee.swift": 2,
    "Views/Library/ViewModes/LibraryModeFixtures.swift": 1,
    "Views/Library/ViewModes/LibraryView+CellDrop.swift": 1,
    "Views/Library/ViewModes/LibraryView+Helpers.swift": 2,
    "Views/Library/ViewModes/Table/ClaimsTableView.swift": 1,
    "Views/Library/ViewModes/Table/EntitiesTableView.swift": 1,
    "Views/Library/ViewModes/Table/LibraryOutlineRowDrag.swift": 1,
    "Views/Library/ViewModes/Table/LibraryTableDisclosureAlignment.swift": 1,
    "Views/Library/Workspace/LibraryWorkspaceRoot.swift": 2,
    "Views/Library/Workspace/WorkspaceItemPicker.swift": 1,
    "Views/LooveCoverage/LooveCoverageLanguageCatalog.swift": 1,
    "Views/LooveCoverage/LooveCoverageModels.swift": 2,
    "Views/Models/ModelFinderView.swift": 2,
    "Views/Onboarding/BakeoffSection.swift": 1,
    "Views/Onboarding/FirstRun/FirstRunWindow+Models.swift": 1,
    "Views/Onboarding/FirstRun/FirstRunWindow+Pager.swift": 1,
    "Views/Onboarding/FirstRun/FirstRunWindow+Previews.swift": 1,
    "Views/Onboarding/FirstRun/PagerTrackpadSwipe.swift": 1,
    "Views/Onboarding/InspectorProjectEmbedding.swift": 2,
    "Views/Onboarding/KeptExportFields.swift": 2,
    "Views/Onboarding/Questions/RecipeConditionFields.swift": 1,
    "Views/Onboarding/Questions/RecipeHowFields.swift": 1,
    "Views/Onboarding/Questions/RecipeReadyReadsViews.swift": 2,
    "Views/Onboarding/RecipeCloudCapViews.swift": 4,
    "Views/Onboarding/RecipeCodeTokenField.swift": 2,
    "Views/Onboarding/RecipePlanEditing.swift": 4,
    "Views/Onboarding/RecipeReadyFields.swift": 1,
    "Views/Onboarding/RecipeSetupFields.swift": 6,
    "Views/Onboarding/RecipeSetupInspectorSections.swift": 5,
    "Views/Onboarding/RecipeSetupModelRows.swift": 6,
    "Views/Onboarding/RecipeSetupPlanFields.swift": 8,
    "Views/Onboarding/RecipeStepsView.swift": 1,
    "Views/Onboarding/RecipeTrainOffersFields.swift": 1,
    "Views/Onboarding/RecipeWhenWhereHandFields.swift": 1,
    "Views/Onboarding/Stages/PrepareImagesCard.swift": 2,
    "Views/Onboarding/Stages/PrepareImagesCheckList.swift": 1,
    "Views/Onboarding/Stages/RenditionChainStripView.swift": 1,
    "Views/Onboarding/Stages/ReviewInstructionsEditor.swift": 1,
    "Views/Onboarding/Stages/SetupStageChooser.swift": 2,
    "Views/Onboarding/Stages/SetupStagePage.swift": 1,
    "Views/Onboarding/Stages/SetupStageSamples.swift": 2,
    "Views/Onboarding/Stages/SharingStageSection.swift": 4,
    "Views/Onboarding/Stages/Showcase/StagePageLayer.swift": 3,
    "Views/Onboarding/Stages/Showcase/StagePictures+Knowledge.swift": 12,
    "Views/Onboarding/Stages/Showcase/StagePictures+Operations.swift": 4,
    "Views/Onboarding/Stages/Showcase/StagePictures+Page.swift": 10,
    "Views/Onboarding/Stages/Showcase/StageShowcaseSection.swift": 1,
    "Views/Onboarding/Stages/Showcase/StageShowcaseView.swift": 1,
    "Views/Onboarding/Stages/StageCandidateChooser.swift": 1,
    "Views/Onboarding/Stages/StageCompareWindow.swift": 2,
    "Views/Onboarding/Stages/StageKindsField.swift": 1,
    "Views/Onboarding/WhatFicheroRunsFields.swift": 3,
    "Views/Preview/EditorView.swift": 1,
    "Views/Preview/EntrySourcePreview.swift": 1,
    "Views/Preview/FolderContentsPreview.swift": 1,
    "Views/Preview/FolderRowsPreview.swift": 1,
    "Views/Preview/FolderViewPreview.swift": 1,
    "Views/Preview/ImageEditor/ImageBatchPrepareSheet.swift": 1,
    "Views/Preview/ImageEditor/ImageEditorView+Types.swift": 1,
    "Views/Preview/ImageEditor/ImageMarqueeOverlay.swift": 1,
    "Views/Preview/ImageEditor/PageCornerHandles.swift": 1,
    "Views/Preview/ImageEditor/PageRegionOutline.swift": 1,
    "Views/Preview/ImageViewer/AnnotationMarkRendering.swift": 3,
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingIOS.swift": 2,
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift": 1,
    "Views/Preview/ImageViewer/FullScreenImagePreviewIOSOnly.swift": 3,
    "Views/Preview/ImageViewer/Layers/ImageLayer.swift": 1,
    "Views/Preview/ImageViewer/MagnifierPanel.swift": 3,
    "Views/Preview/ImageViewer/NavigatorMiniMap.swift": 1,
    "Views/Preview/ImageViewer/PreviewZoomMapCluster.swift": 1,
    "Views/Preview/ImageViewer/Regions/DocumentOverlay.swift": 1,
    "Views/Preview/ImageViewer/Regions/PreviewPointerFeed.swift": 1,
    "Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift": 1,
    "Views/Preview/ImageViewer/Regions/RegionNaming.swift": 1,
    "Views/Preview/ImageViewer/Regions/SegmentEditingMode.swift": 1,
    "Views/Preview/ImageViewer/Regions/ShapeDrawing.swift": 1,
    "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+Annotations.swift": 1,
    "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+RegionEntry.swift": 1,
    "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+Regions.swift": 1,
    "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+SegmentEdits.swift": 1,
    "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+SegmentSelectionEdits.swift": 1,
    "Views/Preview/ImageViewer/ScrollWheelZoom.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewIOS.swift": 2,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac+EventHandlers.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac+Overlays.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac+PageNav.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac+Renditions.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac+ZoomActions.swift": 1,
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift": 2,
    "Views/Preview/MediaStreamPreview.swift": 1,
    "Views/Preview/PDFViewer/PDFLoupeOverlay.swift": 1,
    "Views/Preview/PDFViewer/PDFPageControllers.swift": 2,
    "Views/Preview/PDFViewer/PDFPageView+Reshape.swift": 1,
    "Views/Preview/PDFViewer/PDFPageView.swift": 1,
    "Views/Preview/PreviewFolderViewEnvironment.swift": 1,
    "Views/Preview/PreviewInitialZoomPolicy.swift": 1,
    "Views/Preview/QuickLookViewer/QuickLookComponents.swift": 1,
    "Views/Preview/QuickLookViewer/QuickLookPreviewViews.swift": 5,
    "Views/Preview/ReaderPreviewLinking.swift": 1,
    "Views/Preview/SourcePaneImageControls.swift": 1,
    "Views/Prototypes/PrototypeEditorSheet.swift": 1,
    "Views/Reader/Disagreement/ReaderDisagreementView.swift": 1,
    "Views/Reader/Knowledge/DocumentKGSurface.swift": 1,
    "Views/Reader/Knowledge/DocumentKGSurfaceTypes.swift": 2,
    "Views/Reader/Knowledge/DocumentKGWebPane+Route.swift": 1,
    "Views/Reader/Knowledge/DocumentKGWebPane+Scripts.swift": 1,
    "Views/Reader/Knowledge/DocumentKGWebPane+Theme.swift": 1,
    "Views/Reader/Knowledge/DocumentKGWebPane.swift": 1,
    "Views/Reader/Knowledge/DocumentKGWebPaneCoordinator+Recovery.swift": 1,
    "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift": 2,
    "Views/Reader/Knowledge/ReaderFindInPage.swift": 2,
    "Views/Reader/Knowledge/ReaderTextEdit.swift": 1,
    "Views/Reader/Page/DocumentTextReader.swift": 1,
    "Views/Reader/Page/Immersive/KeyboardExitCatcher.swift": 2,
    "Views/Reader/Page/Lenses/ReaderArtifactDiff.swift": 1,
    "Views/Reader/Page/Lenses/ReaderArtifactLensContent.swift": 1,
    "Views/Reader/Page/Lenses/ReaderArtifactMenu.swift": 1,
    "Views/Reader/Page/Lenses/ReadingPaneView+ArtifactCompare.swift": 1,
    "Views/Reader/Page/Lenses/ReadingPaneView+ArtifactLens.swift": 2,
    "Views/Reader/Page/Lines/ReaderLineVersions.swift": 3,
    "Views/Reader/Page/Lines/ReaderLinesView.swift": 1,
    "Views/Reader/Page/ReaderPassageAnchor.swift": 1,
    "Views/Reader/Page/Tries/TryLabelButton.swift": 1,
    "Views/Reader/ReaderHighlightLayers.swift": 2,
    "Views/Reader/ReaderMarkdownDrag.swift": 1,
    "Views/Reader/ReaderPageActivationState.swift": 1,
    "Views/Reader/ReaderToolbar.swift": 1,
    "Views/Reader/ReaderToolbarCluster.swift": 2,
    "Views/Reader/ReaderToolbarTypes.swift": 2,
    "Views/Reader/Surfaces/ReaderTab.swift": 1,
    "Views/Reader/TextReadoutToggles.swift": 1,
    "Views/Segments/CorrectThisLine.swift": 1,
    "Views/Segments/FlaggedLineMark.swift": 2,
    "Views/Segments/SegmentsOtherReadingsMenu.swift": 2,
    "Views/Settings/AI/AIProviders/AIModelCatalog.swift": 2,
    "Views/Settings/AI/AIProviders/AIModelSelectionView.swift": 1,
    "Views/Settings/AI/AIProviders/AIProviderAddModelsSheet.swift": 1,
    "Views/Settings/AI/AIProviders/AddProviderSheet.swift": 1,
    "Views/Settings/AI/AIProviders/ProvidersView+ModelTypes.swift": 2,
    "Views/Settings/AI/AIProviders/ProvidersView+ProviderDetailView.swift": 2,
    "Views/Settings/AI/AIProviders/ProvidersView+ProviderSettingsRow.swift": 1,
    "Views/Settings/AI/AISettingsView.swift": 1,
    "Views/Settings/AI/LocalRuntimeModelsView.swift": 1,
    "Views/Settings/AI/SettingsModelDownload.swift": 1,
    "Views/Settings/Engine/ServerSettingsModel.swift": 2,
    "Views/Settings/General/RunAutomaticallySetting.swift": 2,
    "Views/Settings/History/AuditHistoryView.swift": 1,
    "Views/Settings/MCP/MCPServersView.swift": 1,
    "Views/Settings/SettingsDetailHeader.swift": 1,
    "Views/Settings/SettingsGroupContainers.swift": 3,
    "Views/Settings/SettingsView.swift": 1,
    "Views/Settings/SettingsViewPanes.swift": 2,
    "Views/Settings/Sharing/Access/AccessMatrixView.swift": 1,
    "Views/Settings/Sharing/AccountsPaneModel.swift": 1,
    "Views/Settings/Sharing/CaptureSettingsView.swift": 1,
    "Views/Settings/Sharing/InviteAccountSection.swift": 2,
    "Views/Settings/Sharing/Pairing/MacRemoteClientPairingSection.swift": 1,
    "Views/Settings/Sharing/Pairing/PairingCardView.swift": 1,
    "Views/Settings/Sharing/Share/AddressLines.swift": 1,
    "Views/Settings/Sharing/Share/ShareWhichProjectsSheet.swift": 1,
    "Views/Settings/Sharing/SharingPaneModel.swift": 1,
    "Views/Settings/Sharing/TurnOnAccountsSheet.swift": 1,
    "Views/Settings/Sharing/UsersSettingsView.swift": 1,
    "Views/Settings/Snapshots/SnapshotsView.swift": 1,
    "Views/Sharing/AgentConsent/AgentConsentSheet.swift": 1,
    "Views/Sharing/AgentConsent/AgentConsentStore.swift": 1,
    "Views/Shell/ContentView/Actions/ToolbarAndChatRoutes.swift": 2,
    "Views/Shell/ContentView/ContentView+SidebarButtons.swift": 1,
    "Views/Shell/ContentView/ContentView.swift": 1,
    "Views/Shell/ContentView/ContentViewModifiers.swift": 2,
    "Views/Shell/ContentView/DocumentStoreChangeObserver.swift": 1,
    "Views/Shell/ContentView/Layout/PaneSpec.swift": 1,
    "Views/Shell/ContentView/Layout/ToolbarTextModeSync.swift": 1,
    "Views/Shell/ContentView/SidebarMultiSelectionScope.swift": 1,
    "Views/Shell/ContentView/SidebarSelectionObserver.swift": 1,
    "Views/Shell/ContentViewHelperViews.swift": 3,
    "Views/Shell/ConversionNotice.swift": 1,
    "Views/Shell/LibraryServiceEnvironment.swift": 1,
    "Views/Shell/OpenAffordances.swift": 4,
    "Views/Shell/PaneHead/LibraryPathCrumbs.swift": 1,
    "Views/Shell/PaneHead/PaneChromeMenu.swift": 2,
    "Views/Shell/PaneHead/PaneHead.swift": 2,
    "Views/Shell/PaneHead/PaneKindSelector.swift": 2,
    "Views/Shell/PaneHead/PreviewHeadControls.swift": 4,
    "Views/Shell/PaneHead/PreviewPaneChrome.swift": 1,
    "Views/Shell/PaneScopedOption.swift": 1,
    "Views/Shell/PaneSurface.swift": 1,
    "Views/Shell/PaneVisibility.swift": 1,
    "Views/Shell/SheetLibraryEnvironment.swift": 1,
    "Views/Shell/ShellLayoutPolicy.swift": 2,
    "Views/Shell/SurfaceTabBar.swift": 1,
    "Views/Shell/Toolbar/AnnotationBar.swift": 3,
    "Views/Shell/Toolbar/LibraryToolbarPolicy.swift": 2,
    "Views/Shell/Toolbar/ModelChipToolbarItem.swift": 2,
    "Views/Shell/Toolbar/SharedModelPicker/SharedModelListBuilder.swift": 1,
    "Views/Shell/Toolbar/StagedWorkflowStep.swift": 1,
    "Views/Shell/Toolbar/StatusIslandToolbarItem.swift": 1,
    "Views/Shell/Toolbar/ToolbarSurfaceToggleStyle.swift": 1,
    "Views/Shell/Toolbar/WorkflowBarChainStyling.swift": 2,
    "Views/Shell/Toolbar/WorkflowBarModelPicker.swift": 1,
    "Views/Shell/Toolbar/WorkflowBarModelTier.swift": 1,
    "Views/Shell/Toolbar/WorkflowComparePlan.swift": 1,
    "Views/Shell/Toolbar/WorkflowRunRegistry.swift": 1,
    "Views/Shell/Toolbar/WorkflowStepsDisclosure.swift": 1,
    "Views/Shell/WindowLayout/WindowWorkspace.swift": 1,
    "Views/Shell/WindowLayout/WorkspaceLayoutPreview.swift": 1,
    "Views/Sidebar/Components/SidebarActions.swift": 1,
    "Views/Sidebar/Components/SidebarCreationHandlers.swift": 1,
    "Views/Sidebar/Components/SidebarObservers.swift": 1,
    "Views/Sidebar/ItemRow/SidebarDragID.swift": 2,
    "Views/Sidebar/ItemRow/SidebarDropClassification.swift": 2,
    "Views/Sidebar/ItemRow/SidebarDropFeedback.swift": 1,
    "Views/Sidebar/ItemRow/SidebarDropOperation.swift": 1,
    "Views/Sidebar/ItemRow/SidebarDropProviderReader.swift": 2,
    "Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift": 1,
    "Views/Sidebar/ItemRow/SidebarPreviewCatalog.swift": 1,
    "Views/Sidebar/ItemRow/SidebarRowLabelCore.swift": 1,
    "Views/Sidebar/Sections/LibraryHeaderRow.swift": 1,
    "Views/Sidebar/Sections/SidebarBottomToolbar.swift": 1,
    "Views/Sidebar/Sections/SidebarContextTargets.swift": 1,
    "Views/Sidebar/Sections/SidebarKnowledgeRows.swift": 2,
    "Views/Sidebar/Sections/SidebarMetadata.swift": 1,
    "Views/Sidebar/Sections/SidebarModelsNode.swift": 1,
    "Views/Sidebar/Sections/SidebarSectionHeader.swift": 1,
    "Views/Sidebar/Sections/SidebarViewExtensions.swift": 1,
    "Views/Sidebar/Sharing/PairedMachineRowView.swift": 2,
    "Views/Sidebar/State/ActivityDataProcessing.swift": 1,
    "Views/Sidebar/State/SidebarConstants.swift": 1,
    "Views/Sidebar/State/SidebarStateManagers.swift": 2,
    "Views/Sidebar/Trash/SidebarTrashDrop.swift": 1,
    "Views/Sidebar/Trash/SidebarTrashNode.swift": 2,
    "Views/Sidebar/Trash/SidebarTrashRow.swift": 1,
    "Views/Workflow/Canvas/CanvasHelpers.swift": 2,
    "Views/Workflow/Canvas/WorkflowCanvasMath.swift": 2,
    "Views/Workflow/Canvas/WorkflowCanvasView.swift": 1,
    "Views/Workflow/Canvas/WorkflowDiagramPreview.swift": 1,
    "Views/Workflow/Canvas/WorkflowEdgeView+Dragging.swift": 1,
    "Views/Workflow/Canvas/WorkflowEdgeView+Edges.swift": 2,
    "Views/Workflow/Canvas/WorkflowEdgeView+Helpers.swift": 2,
    "Views/Workflow/Canvas/WorkflowMermaidView.swift": 1,
    "Views/Workflow/Canvas/WorkflowPortView.swift": 1,
    "Views/Workflow/Editor/SimpleWorkflowView.swift": 1,
    "Views/Workflow/Editor/WorkflowEditor+Preview.swift": 2,
    "Views/Workflow/Editor/WorkflowGraphLayout.swift": 2,
    "Views/Workflow/Execution/BatchRunView.swift": 1,
    "Views/Workflow/Execution/WorkflowExecutionView.swift": 1,
    "Views/Workflow/Execution/WorkflowOutputLog+ErrorCell.swift": 1,
    "Views/Workflow/Execution/WorkflowOutputLog+Models.swift": 2,
    "Views/Workflow/Execution/WorkflowOutputLog.swift": 1,
    "Views/Workflow/Library/WorkflowLibraryView.swift": 1,
    "Views/Workflow/Library/WorkflowLibraryViewParts/WorkflowDetailView.swift": 1,
    "Views/Workflow/Library/WorkflowLibraryViewParts/WorkflowMiniPreview.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/CollectionNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/DescribeNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/ExtractEntitiesNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/FilesNodeConfig+PickerViews.swift": 2,
    "Views/Workflow/Nodes/NodeConfigs/FilesNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/NodeConfigView.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/NodePromptEditor.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/SearchNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/SummarizeCollectionNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/SummarizeFileNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/SummarizeFolderNodeConfig.swift": 1,
    "Views/Workflow/Nodes/NodeConfigs/TranscribeNodeConfig.swift": 2,
    "Views/Workflow/Nodes/NodeConfigs/ZoomNodeConfig.swift": 2,
    "Views/Workflow/Nodes/NodeInputMappings.swift": 1,
    "Views/Workflow/Nodes/NodeProviderModelSelector.swift": 1,
    "Views/Workflow/Nodes/WorkflowNodeView.swift": 1,
    "Views/Workflow/Nodes/WorkflowToolBlocks.swift": 2,
}


def compare(found: dict[str, list[str]], known: dict[str, int]) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """(files above their baseline, files now below it, baseline entries now clean)."""
    over = {rel: f for rel, f in found.items() if len(f) > known.get(rel, 0)}
    below = sorted(rel for rel, f in found.items() if rel in known and len(f) < known[rel])
    clean = sorted(rel for rel in known if rel not in found)
    return over, below, clean


def _plant(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


_CLEAN = {
    "Views/Library/LibraryRow.swift": "import SwiftUI\nstruct LibraryRow: View {\n var body: some View { Text(\"struct Other\") }\n}\nprivate struct Helper {}\n#Preview { LibraryRow() }\n",
    "Views/Library/LibraryRowModel.swift": "// struct Fake {}\nstruct LibraryRowModel {}\n",
    "Views/Library/LibraryRow+Menu.swift": "extension LibraryRow {}\nprivate struct Extra {}\n",
    "Views/Library/ReaderView.swift": "struct ReaderView: View {}\nprivate struct ReaderViewModel {}\n",
    "Services/Thing/ThingTypes.swift": "struct A {}\nstruct B {}\nenum C {}\n",
    "App/Menus/FileCommands.swift": "struct FileCommands: View {}\n",
    "App/MainScene.swift": "struct MainScene: View {}\n",
    "Models/Thing.swift": "final class Thing {}\n",
    "Models/Generated/WireGenerated.swift": "struct One {}\nstruct Two {}\n",
}
_DIRTY = {  # file -> the rule it must trip
    "Models/Pair.swift": "one-type",
    "Models/Wrong.swift": "file-name",
    "Models/Thing+Topic.swift": "file-name",
    "Views/Library/Odd.swift": "view-shape",
    "Models/Stray.swift": "view-place",
    "Views/Library/ReaderiOSOnly.swift": "platform",
    "Views/Library/PaneiOS.swift": "platform",
}
_DIRTY_TEXT = {
    "Models/Pair.swift": "struct Pair {}\nstruct Pair2 {}\n",
    "Models/Wrong.swift": "struct Other {}\n",
    "Models/Thing+Topic.swift": "extension Elsewhere {}\n",
    "Views/Library/Odd.swift": "struct Odd: View {}\n",
    "Models/Stray.swift": "struct StrayView: View {}\n",
    "Views/Library/ReaderiOSOnly.swift": "struct ReaderiOSOnly {}\n",
    "Views/Library/PaneiOS.swift": "struct PaneiOS {}\n",
}


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "fichero" / "fichero"
        _plant(root, _CLEAN)
        found, _ = scan(root)
        if found:
            print("self-test FAILED: clean files reported:", found, file=sys.stderr)
            return 1
        _plant(root, _DIRTY_TEXT)
        found, _ = scan(root)
        for rel, rule in _DIRTY.items():
            if not any(f.startswith(rule) for f in found.get(rel, [])):
                print(f"self-test FAILED: {rel} should trip {rule}, got {found.get(rel)}", file=sys.stderr)
                return 1
        if set(found) - set(_DIRTY):
            print("self-test FAILED: extra files reported:", sorted(set(found) - set(_DIRTY)), file=sys.stderr)
            return 1
        over, _, _ = compare(found, {rel: len(f) for rel, f in found.items()})
        worse, _, _ = compare(found, {rel: len(f) - 1 for rel, f in found.items()})
        if over or set(worse) != set(found):
            print("self-test FAILED: the baseline comparison does not ratchet", file=sys.stderr)
            return 1
    print("self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    if "--self-test" in argv:
        return _self_test()
    found, count = scan()
    require_scan_floor(count, FLOOR, "app Swift files (about 1,700 on 2026-11-15)")
    if "--list" in argv:
        for rel, items in found.items():
            for item in items:
                print(f"{rel}: {item}")
        return 0
    if "--generate" in argv:
        print("KNOWN_VIOLATIONS: dict[str, int] = {")
        for rel, items in found.items():
            print(f'    "{rel}": {len(items)},')
        print("}")
        return 0
    over, below, clean = compare(found, KNOWN_VIOLATIONS)
    print(f"check_swift_one_type_per_file: {count} Swift files scanned, {len(found)} with findings, {len(KNOWN_VIOLATIONS)} baselined")
    if below or clean:
        print(f"  ✓ {len(below) + len(clean)} baselined file(s) improved — lower or drop their KNOWN_VIOLATIONS entries")
    if over:
        for rel, items in over.items():
            for item in items:
                print(f"  ✗ {rel}: {item}")
        print(f"\n{len(over)} file(s) above their baseline (spec: code-organization, code-org.naming.swift-file-is-type).")
        return 1
    print("✓ No Swift file above its baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
