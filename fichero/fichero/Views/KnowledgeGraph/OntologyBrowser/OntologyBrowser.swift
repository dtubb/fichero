import FicheroAPIClient
import SwiftUI

/// Equatable focused-value wrapper for the global Knowledge Graph view mode.
/// Mirrors `DocumentRepresentationFocus` (#2032): keys equality on the value so
/// SwiftUI dedupes the focused value, letting the View-menu / main-toolbar
/// switcher drive the focused `OntologyBrowser` without per-frame churn. Lets
/// the KG mode switcher live in the menu/toolbar instead of a segmented icon
/// row inside the KG pane toolbar (#2436).
struct KnowledgeGraphViewModeFocus: Equatable {
    let current: OntologyBrowser.ViewMode
    let select: (OntologyBrowser.ViewMode) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.current == rhs.current
    }
}

/// Browser panel for exploring entities and their associated claims.
/// Wires #498 — per-library Knowledge Graph view, peer to Workflows
/// and Activity. Uses `EntityServiceGenerated` (\`/api/entities\` +
/// \`/api/claims\`).
///
/// The view is split across focused files (#1703):
/// - `OntologyBrowser+Toolbar.swift` — toolbar, tools menu, filter menu
/// - `OntologyBrowser+List.swift` — entity list sidebar, search, navigation
/// - `OntologyBrowser+Detail.swift` — entity detail panel + claim loading
/// - `ForceDirectedGraphView.swift`, `OntologyBrowserGraphModel.swift`,
///   `HeuristicReviewSheet.swift`, `NewEntitySheet.swift`,
///   `EntityKindChartView.swift` — standalone companion types.
struct OntologyBrowser: View {
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    /// Observable claim store (#1862) — its `changeToken` drives detail-panel
    /// resync, replacing the retired `.ficheroClaim*` NotificationCenter bus.
    @Environment(ClaimStore.self) var claimStore
    @Environment(EntityStore.self) var entityStore
    /// Finder-style Open in New Tab / New Window for ontology rows (#1685).
    @Environment(\.openWindow) var openWindow
    /// Compact width (iPhone) collapses the list|detail split into a push flow (#3011).
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @State var loadState = OntologyBrowserLoadState()
    @SceneStorage("ontology.selectedEntityId") var selectedEntityId: String?
    @State var navHistory = NavigationHistoryManager()
    @State var isNavigatingHistory = false
    @State var searchText = ""
    @State var isSearching = false
    @State var isDateBucketExpanded = false
    @State var graphScrollSync = DocumentScrollSyncState()

    /// Swap the detail pane between entity-claims view (default) and a
    /// force-directed graph over the filtered entity set. (#902, partial #889)
    enum ViewMode: String, CaseIterable, Identifiable {
        case list, graph, chart, timeline, map
        var id: String { rawValue }
        var label: String {
            switch self {
            case .list: return "List"
            case .graph: return "Graph"
            case .chart: return "Chart"
            case .timeline: return "Timeline"
            case .map: return "Map"
            }
        }
        var icon: String {
            switch self {
            case .list: return "list.bullet"
            case .graph: return "circle.grid.cross"
            case .chart: return "chart.bar"
            case .timeline: return "calendar.day.timeline.left"
            case .map: return "map"
            }
        }

        var helpText: String {
            switch self {
            case .list: return "List — browse entities and their claims"
            case .graph: return "Graph — force-directed network of entity relationships"
            case .chart: return "Chart — entity counts by type"
            case .timeline: return "Timeline — entities arranged by date"
            case .map: return "Map — geographic entities on a map"
            }
        }
    }
    @SceneStorage("ontology.viewMode") var viewModeRaw: String = ViewMode.list.rawValue
    var viewMode: ViewMode {
        ViewMode(rawValue: viewModeRaw) ?? .list
    }
    var viewModeBinding: Binding<ViewMode> {
        Binding(
            get: { ViewMode(rawValue: viewModeRaw) ?? .list },
            set: { viewModeRaw = $0.rawValue }
        )
    }

    /// Shared with the document-inspector KG tab (`inspector.kg.hiddenKinds`)
    /// so toggling a kind in one place updates the other. #887. Empty
    /// CSV = show every entity kind (default).
    @AppStorage("inspector.kg.hiddenKinds")
    var hiddenKindsCSV: String = ""

    /// When true, entities whose canonical name looks like OCR noise are
    /// hidden from the list and graph (#1168). Persisted so the user's
    /// preference survives restarts.
    @AppStorage("ontology.suppressOcrGarbage")
    var suppressOcrGarbage: Bool = true

    /// Persisted entity-list pane width (#1034). AppStorage so it survives
    /// app restarts; 240pt default is narrower than the old 280pt to give
    /// the detail pane more room.
    @AppStorage("ontology.entityListWidth")
    var entityListWidth: Double = 240

    @State var toolStatus: String?
    @State var pendingPredictions: Components.Schemas.HeuristicPredictionsResponse?
    @State var showCreateSheet = false
    /// Presents the W3C SPARQL query console (#3298).
    @State var showSparqlConsole = false
    @State var entityPendingDeletion: Components.Schemas.KnowledgeEntity?
    @State var entityPendingEdit: Components.Schemas.KnowledgeEntity?
    @State var entityPendingMerge: Components.Schemas.KnowledgeEntity?
    @State var entityPendingSplit: Components.Schemas.KnowledgeEntity?

    var hiddenKinds: Set<String> {
        Self.parseHiddenKinds(hiddenKindsCSV)
    }

    /// Pure helper for parsing the persisted CSV. Exposed for tests
    /// (\`@testable import Fichero\`).
    static func parseHiddenKinds(_ csv: String) -> Set<String> {
        Set(
            csv.split(separator: ",")
                .map { String($0) }
                .filter { !$0.isEmpty }
        )
    }

    /// Returns true if `name` looks like OCR noise rather than a meaningful
    /// entity name. Heuristics: single character, all-numeric, or fewer than
    /// half the characters are letters (#1168).
    static func isOcrGarbage(_ name: String) -> Bool {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        guard trimmedName.count >= 2 else { return true }
        if trimmedName.allSatisfy({ !$0.isLetter }) { return true }
        let letterRatio = Double(trimmedName.filter(\.isLetter).count) / Double(trimmedName.count)
        return letterRatio < 0.5
    }

    /// Pure helper for applying the kind filter to an entity list.
    /// When \`hidden\` is empty, returns the input unchanged. Otherwise
    /// drops entities whose entityType raw value is in \`hidden\`. Nil
    /// entityType is treated as "other".
    static func filterEntities(
        _ entities: [Components.Schemas.KnowledgeEntity],
        hidden: Set<String>
    ) -> [Components.Schemas.KnowledgeEntity] {
        guard !hidden.isEmpty else { return entities }
        return entities.filter { entity in
            let kind = entity.entityType?.rawValue ?? "other"
            return !hidden.contains(kind)
        }
    }

    /// Date rows are still returned by older KG data as ordinary entities.
    /// Keep them available without mixing them into the named-entity scan.
    static func isDateEntity(_ entity: Components.Schemas.KnowledgeEntity) -> Bool {
        if entity.entityType?.rawValue.lowercased() == "date" {
            return true
        }
        let name = entity.canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)
        return name.range(
            of: #"^\d{3,4}([-/]\d{1,2}){0,2}(\b|$)"#,
            options: .regularExpression
        ) != nil
        || name.range(
            of: #"^(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?)\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil
        || name.range(
            of: #"^(sep(t)?(ember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil
    }

    // ponytail: recompute inputs — entityStore.libraryEntities, hiddenKindsCSV, suppressOcrGarbage
    @State var filteredEntities: [Components.Schemas.KnowledgeEntity] = []
    @State var nonDateEntities: [Components.Schemas.KnowledgeEntity] = []
    @State var dateEntities: [Components.Schemas.KnowledgeEntity] = []

    func recomputeFilteredEntities() {
        var result = Self.filterEntities(entities, hidden: hiddenKinds)
        if suppressOcrGarbage {
            result = result.filter { !Self.isOcrGarbage($0.canonicalName) }
        }
        filteredEntities = result
        nonDateEntities = result.filter { !Self.isDateEntity($0) }
        dateEntities = result.filter(Self.isDateEntity)
    }

    // MARK: - Load-state accessors

    var entities: [Components.Schemas.KnowledgeEntity] {
        entityStore.libraryEntities
    }
    var claimCounts: [String: Int] {
        entityStore.libraryClaimCounts
    }
    var loadError: String? {
        entityStore.libraryLoadError
    }
    var isLoading: Bool {
        entityStore.isLoadingLibrary
    }
    var entityClaims: [Components.Schemas.KnowledgeClaim] {
        get { loadState.entityClaims }
        nonmutating set { loadState.entityClaims = newValue }
    }
    var isLoadingClaims: Bool {
        get { loadState.isLoadingClaims }
        nonmutating set { loadState.isLoadingClaims = newValue }
    }

    var body: some View {
        browserLayout
        .frame(minWidth: 300, minHeight: 200)
        .modifier(OntologySheetsModifier(browser: self))
        // Publish the active KG view mode so the View menu / main-toolbar View
        // menu drives the switch — the segmented icon row no longer lives in
        // the KG pane toolbar (#2436). Per-window, dedup'd via the Equatable
        // wrapper (same rationale as `documentRepresentation`).
        .focusedSceneValue(
            \.knowledgeGraphViewMode,
            KnowledgeGraphViewModeFocus(
                current: viewMode,
                select: { viewModeRaw = $0.rawValue }
            )
        )
        .onAppear { recomputeFilteredEntities() }
        .onChange(of: entityStore.libraryEntities) { _, _ in recomputeFilteredEntities() }
        .onChange(of: hiddenKindsCSV) { _, _ in recomputeFilteredEntities() }
        .onChange(of: suppressOcrGarbage) { _, _ in recomputeFilteredEntities() }
        .onChange(of: kgFocusState.focusedEntityId) { _, entityId in
            guard let entityId, selectedEntityId != entityId else { return }
            selectedEntityId = entityId
        }
    }

    /// Regular width keeps the two-column list|detail split; compact width
    /// (iPhone) collapses to a list→detail push flow (#3011).
    @ViewBuilder
    private var browserLayout: some View {
        if ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
            compactBrowser
        } else {
            // Toolbar lives INSIDE the entity list pane (#964) so it scopes to
            // the list only, not the detail/preview pane on the right.
            HStack(spacing: 0) {
                entityListColumn
                    .frame(width: entityListWidth)
                ResizableDivider(width: $entityListWidth, minWidth: 220, maxWidth: 420, edge: .leading)
                detailPaneForMode
                    .frame(maxWidth: .infinity)
            }
        }
    }

    /// The entity list pane (its own toolbar + list), shared by both layouts.
    private var entityListColumn: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            entityListSidebar
        }
    }

    /// Compact (iPhone) entity flow (#3011): the entity list is the
    /// `NavigationStack` root; selecting an entity pushes its detail and focuses
    /// it in `KGFocusState`; Back (nil leaf) pops and clears KG focus.
    private var compactBrowser: some View {
        NavigationStack {
            entityListColumn
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .navigationTitle("Entities")
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .navigationDestination(item: $selectedEntityId) { _ in
                    detailPaneForMode
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        #if !os(macOS)
                        .navigationBarTitleDisplayMode(.inline)
                        #endif
                }
                .onChange(of: selectedEntityId) { _, newValue in
                    kgFocusState.syncPushedEntity(newValue)
                }
        }
    }

    /// Renders the detail-pane content based on `viewMode` — either the
    /// existing entity-claims detail or the force-directed graph.
    @ViewBuilder
    var detailPaneForMode: some View {
        switch viewMode {
        case .list:
            entityDetailPanel
        case .graph:
            if let libraryPath = LibraryManager.shared.globalLibrary?.apiClient.currentLibraryPath,
               !libraryPath.isEmpty {
                DocumentKGWebPane(
                    documentId: DocumentKGPaneRoute.globalKGDocumentID,
                    libraryPath: libraryPath,
                    selectedEntityId: selectedEntityId,
                    selectedClaimId: nil,
                    activeTab: KGSurfaceTab.graph.rawValue,
                    activePageNumber: nil,
                    pageCount: nil,
                    onPageSelected: { _ in },
                    scrollSync: graphScrollSync
                )
                .frame(minWidth: 300)
            } else {
                Text("No library selected")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        case .chart:
            EntityKindChartView(entities: filteredEntities)
                .frame(minWidth: 300)
        case .timeline:
            KGTimelineView(
                entities: filteredEntities,
                selectedEntityId: $selectedEntityId
            )
            .frame(minWidth: 300)
        case .map:
            KGMapView(
                entities: filteredEntities,
                selectedEntityId: $selectedEntityId
            )
            .frame(minWidth: 300)
        }
    }

}

extension OntologyBrowser {
    func setHidden(_ kind: String, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.sorted().joined(separator: ",")
    }
}

// MARK: - Previews

#Preview("Browser") {
    OntologyBrowser()
        .frame(width: 600, height: 500)
        .environment(WorkflowExecutionObserver())
        .environment(KGFocusState.shared)
        .environment(LibraryManager.shared.globalLibrary!.claimStore)
        .environment(LibraryManager.shared.globalLibrary!.entityStore)
}

#Preview("Entity Row") {
    List {
        EntityRow(entity: Components.Schemas.KnowledgeEntity(
            id: "entity-1",
            canonicalName: "Napoleon Bonaparte",
            entityType: .person,
            aliases: ["The Emperor", "Napoleon I"],
            description: nil,
            language: "fr",
            metadata: nil,
            mergedIntoId: nil
        ))
    }
    .listStyle(.sidebar)
}
