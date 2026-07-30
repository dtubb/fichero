import FicheroAPIClient
import Observation
import SwiftUI

enum KGGraphRendererFramework: String {
    case cytoscapeWebKit = "cytoscape-webkit"

    static let selected: KGGraphRendererFramework = .cytoscapeWebKit

    var displayName: String {
        switch self {
        case .cytoscapeWebKit:
            return "Cytoscape.js (WebKit)"
        }
    }
}

@MainActor
@Observable
final class DocumentScrollSyncState {
    enum Pane {
        case pdf
        case web
    }

    private var drivingPane: Pane?
    private var releaseTask: Task<Void, Never>?

    func beginDriving(_ pane: Pane) -> Bool {
        guard drivingPane == nil || drivingPane == pane else { return false }
        drivingPane = pane
        releaseTask?.cancel()
        releaseTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(50))
            if self?.drivingPane == pane {
                self?.drivingPane = nil
            }
        }
        return true
    }

    func isDriving(_ pane: Pane) -> Bool {
        drivingPane == pane
    }
}

/// The views the knowledge surface can show. The first three raw values match
/// the tab ids the in-page JS (`document_view.html`) expects.
enum KGSurfaceTab: String, CaseIterable, Identifiable {
    case transcript
    /// Raw value stays "digest" — it is the WIRE CONTRACT with document_view.html
    /// (`data-tab="digest"`, and the literal tab list in its JS). The engine template
    /// is codex's lane, so the USER-FACING name changes here and the wire does not.
    /// What it actually shows: the SVO statements about each entity (#3765).
    case digest
    case graph
    case claims
    case timeline
    case map
    case entities

    var id: String { rawValue }

    /// Human-readable label shown on the native toolbar button.
    var title: String {
        switch self {
        case .transcript: return "Transcript"
        case .digest: return "Statements"
        case .graph: return "Graph"
        case .claims: return "Claims"
        case .timeline: return "Timeline"
        case .map: return "Map"
        case .entities: return "Entities"
        }
    }

    /// SF Symbol mirroring the inspector tab-bar visual language.
    var icon: String {
        switch self {
        case .transcript: return "doc.text"
        case .digest: return "list.bullet.indent"
        case .graph: return "point.3.connected.trianglepath.dotted"
        case .claims: return "quote.bubble"
        case .timeline: return "calendar.badge.clock"
        case .map: return "map"
        case .entities: return "circle.grid.2x2"
        }
    }

    /// Tooltip copy: what the view shows and how to use it. (#1371)
    var helpText: String {
        switch self {
        case .transcript: return "Transcript — read the document's full text"
        case .digest: return "Statements — every subject-verb-object statement we know about this entity"
        case .graph:
            return "Graph — entities and their connections as a network "
            + "(\(KGGraphRendererFramework.selected.displayName))"
        case .claims: return "Claims — statements extracted from the document, grouped by source"
        case .timeline: return "Timeline — dated entities and events in chronological order"
        case .map: return "Map — entities laid out on a visual canvas"
        case .entities: return "Entities — the people, places, and things named in the document"
        }
    }

    /// Number key for the View-menu "Add View" shortcut (⌃⌥⌘N). Mirrors the
    /// menu order; chosen to avoid the ⌘N library-layout and ⌃⌘N sidebar-mode
    /// shortcuts. (#2032)
    var representationShortcut: Character {
        switch self {
        case .transcript: return "1"
        case .digest: return "2"
        case .graph: return "3"
        case .claims: return "4"
        case .timeline: return "5"
        case .map: return "6"
        case .entities: return "7"
        }
    }

    /// True for tabs rendered inside the shared WKWebView (#1346). The KG
    /// visualizations (Entities, Claims, Graph, Timeline, Map) render natively
    /// via inspector / OntologyBrowser components; only the transcript and the
    /// digest summary remain WebKit HTML.
    var usesWebKit: Bool {
        switch self {
        case .transcript, .digest: return true
        case .claims, .entities, .graph, .timeline, .map: return false
        }
    }
}

/// Equatable focused-value wrapper for the active document representation.
///
/// Publishing a raw `Binding<KGSurfaceTab>` via `focusedSceneValue` is a perf
/// footgun: a `Binding` is non-Equatable, so SwiftUI cannot dedupe it and every
/// `body` pass republishes a "new" focused value, causing per-frame
/// invalidation churn ("FocusedValue update tried to update multiple times per
/// frame"). This wrapper keys equality on the *value* (`current`) so the
/// focused value only changes when the active representation actually changes;
/// the `select` closure is excluded from equality (closures are non-Equatable).
/// (#2032)
struct DocumentRepresentationFocus: Equatable {
    let current: KGSurfaceTab
    let select: (KGSurfaceTab) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.current == rhs.current
    }
}

/// Hosts the WebKit document KG plus the native document-scoped claims view.
/// The representation switcher (Transcript/Digest/Graph/Claims/Timeline/Map)
/// lives in the View menu ("Add View"), driven via FocusedValues — not a
/// floating icon bar over the content (#2032 / reform §G).
struct DocumentKGSurface: View {
    let documentId: String
    let documentScope: InspectorClaimDocumentScope
    let libraryPath: String
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    var scrollSync: DocumentScrollSyncState
    /// Zoom level forwarded to the WebKit pane. 1.0 = 100%. (#2316)
    var zoom: Double = 1.0
    /// Active tab driven by the parent pane. When omitted the surface manages
    /// tab state internally (backward-compat for non-split usages).
    /// `= nil` is load-bearing: KnowledgeSurface call site omits these args.
    var externalActiveTab: KGSurfaceTab? = nil // swiftlint:disable:this implicit_optional_initialization
    var onTabSelected: ((KGSurfaceTab) -> Void)? = nil // swiftlint:disable:this implicit_optional_initialization
    /// The full Document, supplied by callers that expose the native Entities
    /// sub-mode (#3503). When nil the surface resolves it from the DocumentStore.
    /// `= nil` is load-bearing: the KnowledgeSurface call site omits it.
    var document: Document? = nil // swiftlint:disable:this implicit_optional_initialization
    /// In-reader find (#4338), forwarded to the WebKit pane. Defaults keep
    /// every existing call site working with find inactive.
    var searchQuery: String = ""
    var searchSelectionIndex: Int = -1
    var onSearchMatchCount: (@MainActor @Sendable (Int) -> Void)?
    /// Pages a run is writing, and their live text (#4357). Forwarded to the
    /// WebKit pane, which patches them in place. Defaults keep every existing
    /// call site working with no run in flight.
    var busyPageNumbers: Set<Int> = []
    var pageContentPatches: [Int: String] = [:]

    @State private var internalActiveTab: KGSurfaceTab = .transcript
    private var activeTab: KGSurfaceTab { externalActiveTab ?? internalActiveTab }

    // Lazy-host latches for the heavy WKWebView on iOS (#2409). `hasAppeared`
    // gates the pane off the first paint so the 6–8s WebContent/GPU/Networking
    // helper-process launch doesn't block the reader's initial layout;
    // `everShownWebKit` keeps a session that stays on the native claims tab from
    // ever spawning the web processes at all. On macOS both are ignored — the
    // pane is cheap and stays alive to preserve scroll (#1346).
    @State private var hasAppeared = false
    @State private var everShownWebKit = false
    @Environment(KGFocusState.self) private var kgFocusState
    @Environment(EntityService.self) private var entityService
    @Environment(ArtifactService.self) private var artifactService
    @Environment(KGCurationService.self) private var kgCurationService
    // For resolving the Document the native Entities sub-mode needs (#3503) when
    // the caller doesn't supply one via `document`.
    @Environment(DocumentStore.self) private var documentStore
    // Document-scoped entities feed the native Graph/Timeline/Map sub-modes (#3503).
    @Environment(EntityStore.self) private var entityStore

    /// The document's entities for the native KG visualizations.
    private var documentEntities: [Components.Schemas.KnowledgeEntity] {
        entityStore.entitiesByDocumentId[documentId] ?? []
    }

    /// Entity selection bound to KG focus so picking a node drives the shared
    /// highlight (the same focus the transcript / claims views observe).
    private var selectedEntityBinding: Binding<String?> {
        Binding(
            get: { selectedEntityId },
            set: { newId in
                if let id = newId { kgFocusState.focusEntity(entityId: id) }
            }
        )
    }

    var body: some View {
        // The representation switcher (Transcript/Digest/Graph/Claims/Timeline/
        // Map) lives in the View menu as "Add View" items, not as a floating
        // icon bar over the content (#2032 / reform §G). Publishing `activeTab`
        // as a focused scene value lets the menu drive the selection for the
        // focused document surface.
        content
            .accessibilityIdentifier("knowledgeSurfaceContent")
            .focusedSceneValue(
                \.documentRepresentation,
                DocumentRepresentationFocus(
                    current: activeTab,
                    select: { selectTab($0) }
                )
            )
    }

    private func selectTab(_ tab: KGSurfaceTab) {
        if onTabSelected != nil {
            onTabSelected?(tab)
        } else {
            internalActiveTab = tab
        }
    }

    /// Whether to host the WKWebView pane this pass. macOS always hosts it (cheap,
    /// preserves scroll, #1346); iOS defers until after first paint and only once
    /// a WebKit tab has been requested, so the heavy helper-process launch never
    /// blocks initial layout and a claims-only session skips it entirely (#2409).
    private var shouldHostWebPane: Bool {
        #if os(iOS)
        return hasAppeared && everShownWebKit
        #else
        return true
        #endif
    }

    @ViewBuilder
    private var content: some View {
        // Keep the WKWebView alive across tab switches via ZStack + opacity
        // so scroll position survives when the user moves between transcript/
        // digest/graph/timeline/map and the native claims tab. (#1346)
        ZStack {
            if shouldHostWebPane {
                DocumentKGWebPane(
                    documentId: documentId,
                    libraryPath: libraryPath,
                    selectedEntityId: selectedEntityId,
                    selectedClaimId: selectedClaimId,
                    activeTab: activeTab.rawValue,
                    activePageNumber: activePageNumber,
                    pageCount: pageCount,
                    onPageSelected: onPageSelected,
                    scrollSync: scrollSync,
                    zoom: zoom,
                    searchQuery: searchQuery,
                    searchSelectionIndex: searchSelectionIndex,
                    onSearchMatchCount: onSearchMatchCount,
                    busyPageNumbers: busyPageNumbers,
                    pageContentPatches: pageContentPatches
                )
                .opacity(activeTab.usesWebKit ? 1 : 0)
                .allowsHitTesting(activeTab.usesWebKit)
            }

            if !activeTab.usesWebKit {
                nativeTabContent
            }
        }
        .onAppear {
            hasAppeared = true
            if activeTab.usesWebKit { everShownWebKit = true }
        }
        .onChange(of: activeTab.usesWebKit) { _, usesWebKit in
            if usesWebKit { everShownWebKit = true }
        }
        // Load the document's entities for the native Graph/Timeline/Map
        // sub-modes (idempotent + cached in the store). (#3503)
        .task(id: documentId) {
            await entityStore.loadEntities(forDocument: documentId)
        }
    }

    @ViewBuilder
    private var nativeTabContent: some View {
        switch activeTab {
        case .transcript, .digest:
            EmptyView()
        case .graph:
            // Native force-directed graph (OntologyBrowser component) over the
            // document's entities — no WebKit (#3503). Nodes are entities, edges
            // their claim co-occurrence; selecting a node drives KG focus.
            ForceDirectedGraphView(
                entities: documentEntities,
                selectedEntityId: selectedEntityBinding
            )
        case .timeline:
            // Native timeline (OntologyBrowser component): the document's
            // entities' dated claims on a time axis (#3503).
            KGTimelineView(
                entities: documentEntities,
                selectedEntityId: selectedEntityBinding
            )
        case .map:
            // Native map (OntologyBrowser component): the document's entities'
            // geo-located claims (#3503).
            KGMapView(
                entities: documentEntities,
                selectedEntityId: selectedEntityBinding
            )
        case .claims:
            // No outer ScrollView — KnowledgeGraphInspectorSection owns its own
            // scroll + pinned bottom mini-toolbar (#3461).
            KnowledgeGraphInspectorSection(
                documentId: documentId,
                documentScope: documentScope,
                entityService: entityService,
                artifactService: artifactService,
                kgCurationService: kgCurationService,
                onClaimSelect: { claimId, _, sourceDocId, pageLabel, _, _ in
                    kgFocusState.focusClaim(
                        claimId: claimId,
                        sourceDocumentId: sourceDocId,
                        sourcePageLabel: pageLabel
                    )
                }
            )
        case .entities:
            // Native document-scoped entity list, reusing the inspector's
            // entities surface (#3503). Selecting an entity drives KG focus so
            // the graph / transcript highlight follows.
            if let doc = document ?? documentStore.currentDocuments.first(where: { $0.id == documentId }) {
                DocumentInspectorEntitiesTab(
                    document: doc,
                    documentId: documentId,
                    selectedEntityId: selectedEntityId,
                    onEntitySelect: { entityId in kgFocusState.focusEntity(entityId: entityId) }
                )
            } else {
                Text("Select a document to see its entities.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

}
