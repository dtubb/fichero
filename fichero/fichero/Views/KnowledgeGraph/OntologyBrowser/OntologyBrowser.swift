// swiftlint:disable file_length
// This file hosts both OntologyBrowser AND ForceDirectedGraphView
// because the KnowledgeGraph PBXGroup isn't file-system synchronized,
// so a separate .swift file would need pbxproj surgery. The 1000-line
// limit is intentionally suppressed; the two View structs are
// independently small and the type_body_length warning still applies
// to each individually.
import FicheroAPIClient
import SwiftUI

/// Browser panel for exploring entities and their associated claims.
/// Wires #498 — per-library Knowledge Graph view, peer to Workflows
/// and Activity. Uses `EntityServiceGenerated` (\`/api/entities\` +
/// \`/api/claims\`).
struct OntologyBrowser: View { // swiftlint:disable:this type_body_length
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(KGFocusState.self) private var kgFocusState
    @StateObject private var loadState = OntologyBrowserLoadState()
    @SceneStorage("ontology.selectedEntityId") private var selectedEntityId: String?
    @State private var navHistory = NavigationHistoryManager()
    @State private var isNavigatingHistory = false
    @State private var searchText = ""
    @State private var isSearching = false
    @State private var isDateBucketExpanded = false
    @StateObject private var graphScrollSync = DocumentScrollSyncState()

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
    }
    @SceneStorage("ontology.viewMode") private var viewModeRaw: String = ViewMode.list.rawValue
    private var viewMode: ViewMode {
        ViewMode(rawValue: viewModeRaw) ?? .list
    }
    private var viewModeBinding: Binding<ViewMode> {
        Binding(
            get: { ViewMode(rawValue: viewModeRaw) ?? .list },
            set: { viewModeRaw = $0.rawValue }
        )
    }

    /// Shared with the document-inspector KG tab (`inspector.kg.hiddenKinds`)
    /// so toggling a kind in one place updates the other. #887. Empty
    /// CSV = show every entity kind (default).
    @AppStorage("inspector.kg.hiddenKinds")
    private var hiddenKindsCSV: String = ""

    /// When true, entities whose canonical name looks like OCR noise are
    /// hidden from the list and graph (#1168). Persisted so the user's
    /// preference survives restarts.
    @AppStorage("ontology.suppressOcrGarbage")
    private var suppressOcrGarbage: Bool = true

    private var hiddenKinds: Set<String> {
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

    private func setHidden(_ kind: String, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.sorted().joined(separator: ",")
    }

    /// Entity-type cases shown in the filter menu. Matches
    /// `EntityType-Output` schema (person/location/organization/event/
    /// concept/other) — keep the order stable for sidebar muscle memory.
    private struct EntityKindChip {
        let key: String
        let label: String
        let icon: String
    }
    private let entityKinds: [EntityKindChip] = [
        .init(key: "person", label: "People", icon: "person.2"),
        .init(key: "location", label: "Places", icon: "mappin.circle"),
        .init(key: "organization", label: "Organizations", icon: "building.2"),
        .init(key: "event", label: "Events", icon: "calendar"),
        .init(key: "concept", label: "Concepts", icon: "tag"),
        .init(key: "other", label: "Other", icon: "questionmark.circle")
    ]

    private var filteredEntities: [Components.Schemas.KnowledgeEntity] {
        var result = Self.filterEntities(entities, hidden: hiddenKinds)
        if suppressOcrGarbage {
            result = result.filter { !Self.isOcrGarbage($0.canonicalName) }
        }
        return result
    }
    private var nonDateEntities: [Components.Schemas.KnowledgeEntity] {
        filteredEntities.filter { !Self.isDateEntity($0) }
    }
    private var dateEntities: [Components.Schemas.KnowledgeEntity] {
        filteredEntities.filter(Self.isDateEntity)
    }

    var body: some View {
        // Toolbar moved INSIDE the entity list pane (#964) so it scopes
        // to the list only — was previously spanning across both panes
        // including the detail / preview area on the right.
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                toolbar
                Divider()
                entityListSidebar
            }
            .frame(width: entityListWidth)
            ResizableDivider(width: $entityListWidth, minWidth: 220, maxWidth: 420, edge: .leading)
            detailPaneForMode
                .frame(maxWidth: .infinity)
        }
        .frame(minWidth: 300, minHeight: 200)
        .sheet(item: Binding(
            get: { pendingPredictions.map(IdentifiedPredictions.init) },
            set: { newValue in pendingPredictions = newValue?.response }
        )) { wrapped in
            HeuristicReviewSheet(response: wrapped.response) {
                pendingPredictions = nil
            }
        }
        .sheet(isPresented: $showCreateSheet) {
            NewEntitySheet { newEntity in
                entities.insert(newEntity, at: 0)
                selectedEntityId = newEntity.id
                showCreateSheet = false
            }
        }
        .sheet(item: Binding(
            get: { entityPendingEdit.map(IdentifiedEntity.init) },
            set: { entityPendingEdit = $0?.entity }
        )) { wrapped in
            NewEntitySheet(editing: wrapped.entity) { updated in
                if let idx = entities.firstIndex(where: { $0.id == updated.id }) {
                    entities[idx] = updated
                }
                entityPendingEdit = nil
            }
        }
        .sheet(item: Binding(
            get: { entityPendingMerge.map(IdentifiedEntity.init) },
            set: { entityPendingMerge = $0?.entity }
        )) { wrapped in
            EntityMergeSheet(
                absorbingEntity: wrapped.entity,
                allEntities: entities
            ) {
                entityPendingMerge = nil
                Task { await loadEntities() }
            }
        }
        .sheet(item: Binding(
            get: { entityPendingSplit.map(IdentifiedEntity.init) },
            set: { entityPendingSplit = $0?.entity }
        )) { wrapped in
            EntitySplitSheet(
                primaryEntity: wrapped.entity,
                allEntities: entities
            ) {
                entityPendingSplit = nil
                Task { await loadEntities() }
            }
        }
        .confirmationDialog(
            "Delete this entity?",
            isPresented: Binding(
                get: { entityPendingDeletion != nil },
                set: { if !$0 { entityPendingDeletion = nil } }
            ),
            presenting: entityPendingDeletion
        ) { entity in
            Button("Delete \(entity.canonicalName)", role: .destructive) {
                Task { await deleteEntity(entity) }
            }
            Button("Cancel", role: .cancel) { entityPendingDeletion = nil }
        } message: { _ in
            Text("The entity will be removed along with any claims that reference it (#901).")
        }
        .onChange(of: kgFocusState.focusedEntityId) { _, entityId in
            guard let entityId, selectedEntityId != entityId else { return }
            selectedEntityId = entityId
        }
    }

    private func deleteEntity(_ entity: Components.Schemas.KnowledgeEntity) async {
        guard let library = LibraryManager.shared.globalLibrary,
              let entityId = entity.id else { return }
        entityPendingDeletion = nil
        do {
            try await library.entityService.deleteEntity(entityId)
            entities.removeAll { $0.id == entityId }
            if selectedEntityId == entityId {
                selectedEntityId = nil
            }
        } catch {
            loadError = "Delete failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Top Toolbar (matches MiniToolbar pattern used elsewhere)

    private var toolbar: some View {
        // The leading "circle.hexagongrid" icon + "Knowledge Graph" text
        // were removed in #981 — the sidebar already labels this
        // destination, and the icon was non-interactive (looked
        // tappable, did nothing). Toolbar now leads straight with
        // actions, ending in the View picker on the right.
        MiniToolbar {
            // Back / forward navigation (#1186)
            Button {
                applyHistoryEntry(navHistory.goBack())
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.plain)
            .disabled(!navHistory.canGoBack)
            .help("Go back (⌘')")
            .keyboardShortcut("'", modifiers: .command)
            Button {
                applyHistoryEntry(navHistory.goForward())
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.plain)
            .disabled(!navHistory.canGoForward)
            .help("Go forward (⌘⇧')")
            .keyboardShortcut("'", modifiers: [.command, .shift])
            Spacer(minLength: 0)
            if let status = toolStatus {
                Text(status)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .transition(.opacity)
            }
            Button {
                showCreateSheet = true
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.plain)
            .help("New entity (#916)")
            toolsMenu
            filterMenu
            Picker("View", selection: viewModeBinding) {
                ForEach(ViewMode.allCases) { mode in
                    Image(systemName: mode.icon).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .fixedSize()
            .help("Switch between list and graph views (#902)")
            // The manual refresh button was removed in #1007 — the
            // entity list now auto-refreshes when a workflow completes
            // (see `.onChange(of: executionObserver.workflowCompletedCount)`
            // on the list .task below). A visible refresh button signals
            // "the data shown might be stale" — better to keep it fresh.
        }
    }

    /// Renders the detail-pane content based on `viewMode` — either the
    /// existing entity-claims detail or the force-directed graph.
    @ViewBuilder
    private var detailPaneForMode: some View {
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

    @State private var toolStatus: String?

    /// "Tools" menu — surfaces the post-consolidation /api/kg/* surfaces:
    /// claim+entity embedding and heuristic prediction generation. Each
    /// action runs in a Task and updates `toolStatus` so the user sees
    /// progress in the toolbar without a modal. (#919 5c)
    private var toolsMenu: some View {
        Menu {
            Button {
                Task { await runEmbedClaims() }
            } label: {
                Label("Embed claims for semantic search", systemImage: "doc.text.magnifyingglass")
            }
            Button {
                Task { await runEmbedEntities() }
            } label: {
                Label("Embed entities for semantic search", systemImage: "magnifyingglass.circle")
            }
            Divider()
            Button {
                Task { await runHeuristicPredictions() }
            } label: {
                Label("Generate suggested links (heuristic)", systemImage: "wand.and.stars")
            }
        } label: {
            Image(systemName: "wrench.and.screwdriver")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Knowledge graph tools")
    }

    private func runEmbedClaims() async {
        await runTool(label: "Embedding claims") { service in
            let count = try await service.embedClaims()
            return "\(count) claims embedded"
        }
    }

    private func runEmbedEntities() async {
        await runTool(label: "Embedding entities") { service in
            let count = try await service.embedEntities()
            return "\(count) entities embedded"
        }
    }

    @State private var pendingPredictions: Components.Schemas.HeuristicPredictionsResponse?
    @State private var showCreateSheet = false
    @State private var entityPendingDeletion: Components.Schemas.KnowledgeEntity?
    @State private var entityPendingEdit: Components.Schemas.KnowledgeEntity?
    @State private var entityPendingMerge: Components.Schemas.KnowledgeEntity?
    @State private var entityPendingSplit: Components.Schemas.KnowledgeEntity?

    private func runHeuristicPredictions() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        toolStatus = "Generating suggestions…"
        defer {
            Task {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                toolStatus = nil
            }
        }
        do {
            let res = try await library.entityService.generateHeuristicPredictions(topK: 10)
            if res.predictions.isEmpty {
                toolStatus = "No new suggestions"
                pendingPredictions = nil
            } else {
                toolStatus = "\(res.predictions.count) suggested links"
                pendingPredictions = res
            }
        } catch {
            toolStatus = "Failed: \(error.localizedDescription)"
        }
    }

    private func runTool(
        label: String,
        action: @escaping (EntityServiceGenerated) async throws -> String
    ) async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        toolStatus = "\(label)…"
        do {
            let result = try await action(library.entityService)
            toolStatus = result
        } catch {
            toolStatus = "Failed: \(error.localizedDescription)"
        }
        // Clear status after a few seconds so the toolbar settles.
        try? await Task.sleep(nanoseconds: 4_000_000_000)
        toolStatus = nil
    }

    /// Filter menu — Tinderbox-style 'displayed attributes' picker,
    /// shared @AppStorage with the inspector KG tab.
    private var filterMenu: some View {
        Menu {
            ForEach(entityKinds, id: \.key) { chip in
                let isHidden = hiddenKinds.contains(chip.key)
                Button {
                    setHidden(chip.key, hidden: !isHidden)
                } label: {
                    Label(chip.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show All") { hiddenKindsCSV = "" }
            Button("Hide All") {
                hiddenKindsCSV = entityKinds
                    .map(\.key)
                    .sorted()
                    .joined(separator: ",")
            }
            Divider()
            Toggle("Suppress OCR noise", isOn: $suppressOcrGarbage)
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter entity kinds")
    }

    // MARK: - Entity List Sidebar

    /// Persisted entity-list pane width (#1034). AppStorage so it survives
    /// app restarts; 240pt default is narrower than the old 280pt to give
    /// the detail pane more room.
    @AppStorage("ontology.entityListWidth")
    private var entityListWidth: Double = 240

    private var entityListSidebar: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            entityList
                .frame(maxWidth: .infinity)  // fill the column, don't anchor left (#981)
        }
    }

    private var searchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)

            TextField("Search entities...", text: $searchText)
                .textFieldStyle(.plain)
                .onSubmit {
                    Task { await searchEntities() }
                }

            if isSearching {
                ProgressView()
                    .scaleEffect(0.7)
            }
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
    }

    private var entities: [Components.Schemas.KnowledgeEntity] {
        get { loadState.entities }
        nonmutating set { loadState.entities = newValue }
    }
    private var claimCounts: [String: Int] {
        get { loadState.claimCounts }
        nonmutating set { loadState.claimCounts = newValue }
    }
    private var loadError: String? {
        get { loadState.loadError }
        nonmutating set { loadState.loadError = newValue }
    }
    private var isLoading: Bool {
        get { loadState.isLoading }
        nonmutating set { loadState.isLoading = newValue }
    }

    private var entityList: some View {
        List(selection: $selectedEntityId) {
            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .listRowBackground(Color.clear)
            } else if let error = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else if filteredEntities.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: entities.isEmpty ? "person.2" : "line.3.horizontal.decrease.circle")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text(entities.isEmpty ? "No Entities" : "All Filtered Out")
                        .font(.subheadline)
                    Text(entities.isEmpty
                            ? "Entities will appear as you create claims"
                            : "Tap a chip above to show entities of that kind")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else {
                ForEach(nonDateEntities, id: \.id) { entity in
                    entityRow(entity)
                }
                if !dateEntities.isEmpty {
                    Section {
                        if isDateBucketExpanded {
                            ForEach(dateEntities, id: \.id) { entity in
                                entityRow(entity)
                            }
                        }
                    } header: {
                        Button {
                            isDateBucketExpanded.toggle()
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: isDateBucketExpanded ? "chevron.down" : "chevron.right")
                                    .font(.caption2.weight(.semibold))
                                    .frame(width: 10)
                                Label("Dates", systemImage: "calendar")
                                Spacer()
                                Text("\(dateEntities.count)")
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .task {
            await loadEntities()
        }
        // #1007/#1008: auto-refresh + re-embed KG data when any workflow
        // finishes. Catalogue / Extract All write KG rows in reduce-phase
        // nodes after all parallel files settle. Embeds run first so the
        // LanceDB index is fresh before heuristic predictions are scored.
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task {
                await loadEntities()
                await runEmbedClaims()
                await runEmbedEntities()
                await runHeuristicPredictions()
            }
        }
        // Push navigation history on entity selection (#1186).
        // isNavigatingHistory prevents re-push while history navigation is driving.
        .onChange(of: selectedEntityId) { _, newValue in
            guard !isNavigatingHistory else { return }
            if let id = newValue {
                navHistory.push(.entityProfile(entityId: id))
                if kgFocusState.focusedClaimId == nil,
                   kgFocusState.focusedEntityId != id {
                    kgFocusState.focusEntity(entityId: id)
                }
            } else {
                navHistory.push(.entityList)
            }
        }
    }

    private func entityRow(_ entity: Components.Schemas.KnowledgeEntity) -> some View {
        EntityRow(entity: entity, claimCount: claimCounts[entity.id ?? ""] ?? 0)
            .tag(entity.id)
            .contextMenu {
                Button("Edit entity…") { entityPendingEdit = entity }
                Button("Merge entities…") { entityPendingMerge = entity }
                Button("Split entity…") { entityPendingSplit = entity }
                Divider()
                Button("Delete entity…", role: .destructive) {
                    entityPendingDeletion = entity
                }
            }
    }

    private func applyHistoryEntry(_ entry: NavigationHistoryManager.Entry?) {
        guard let entry else { return }
        isNavigatingHistory = true
        switch entry {
        case .entityList:
            selectedEntityId = nil
        case .entityProfile(let entityId):
            selectedEntityId = entityId
        case .claimJump, .pdfPage:
            break
        }
        isNavigatingHistory = false
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            async let entityList = service.listEntities(limit: 100)
            async let counts = service.fetchClaimCounts()
            entities = try await entityList
            claimCounts = (try? await counts) ?? [:]
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }

    private func searchEntities() async {
        guard !searchText.isEmpty else {
            await loadEntities()
            return
        }

        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            // EntityServiceGenerated.listEntities supports a free-text
            // `query` filter — same as searching by canonical name or
            // alias. No need for a separate resolve-by-value API.
            entities = try await service.listEntities(query: searchText, limit: 100)
        } catch {
            await loadEntities()
        }

        isLoading = false
    }

    // MARK: - Entity Detail Panel

    private var entityClaims: [Components.Schemas.KnowledgeClaim] {
        get { loadState.entityClaims }
        nonmutating set { loadState.entityClaims = newValue }
    }
    private var isLoadingClaims: Bool {
        get { loadState.isLoadingClaims }
        nonmutating set { loadState.isLoadingClaims = newValue }
    }

    private var entityDetailPanel: some View {
        Group {
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.id == entityId }) {
                EntityDetailView(
                    entity: entity,
                    claims: entityClaims,
                    isLoadingClaims: isLoadingClaims,
                    onNavigateToSource: { claim in
                        ClaimSummaryCard.postOpenClaimSource(for: claim)
                    }
                )
                // `.task(id: entityId)` re-keys on selection change so
                // each entity's claims re-fetch — was previously a bare
                // `.task` that only fired on first appear, leaving the
                // claim list stuck on the first entity's claims even as
                // the header updated. (#965)
                .task(id: entityId) {
                    await loadEntityClaims(entity: entity)
                }
                .onReceive(NotificationCenter.default.publisher(for: .ficheroClaimDeleted)) { _ in
                    Task { await loadEntityClaims(entity: entity) }
                }
                .onReceive(NotificationCenter.default.publisher(for: .ficheroClaimUpdated)) { _ in
                    Task { await loadEntityClaims(entity: entity) }
                }
            } else {
                emptyDetailState
            }
        }
        .frame(minWidth: 250)
    }

    private var emptyDetailState: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.crop.rectangle.stack")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Entity Selected")
                .font(.headline)

            Text("Select an entity to view its details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func loadEntityClaims(entity: Components.Schemas.KnowledgeEntity) async {
        isLoadingClaims = true

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            guard let entityId = entity.id else {
                entityClaims = []
                isLoadingClaims = false
                return
            }
            let sourceDocIds = Set((entity.sourceSupports ?? []).compactMap { $0.sourceDocumentId })
            if sourceDocIds.isEmpty {
                entityClaims = []
                isLoadingClaims = false
                return
            }

            var merged: [String: Components.Schemas.KnowledgeClaim] = [:]
            for docId in sourceDocIds {
                let response = try await service.documentKnowledgeGraph(
                    documentId: docId,
                    includeChildren: true
                )
                for claim in response.claims where (claim.entityIds ?? []).contains(entityId) {
                    if let claimId = claim.id {
                        merged[claimId] = claim
                    }
                }
            }
            entityClaims = merged.values.sorted {
                ($0.createdAt ?? Date.distantPast) > ($1.createdAt ?? Date.distantPast)
            }
        } catch {
            entityClaims = []
        }

        isLoadingClaims = false
    }
}

// MARK: - Heuristic Predictions Review

/// Identifiable wrapper so SwiftUI can drive the .sheet(item:) modifier
/// from an optional struct that isn't itself Identifiable.
private struct IdentifiedPredictions: Identifiable {
    let id = UUID()
    let response: Components.Schemas.HeuristicPredictionsResponse
}

private struct IdentifiedEntity: Identifiable {
    let id = UUID()
    let entity: Components.Schemas.KnowledgeEntity
}

/// Sheet that presents heuristic-prediction candidates with accept/
/// reject actions. Accept calls POST /api/claims/{id}/links to write
/// a KnowledgeClaimLink with relation_type=related_to and link_quality
/// = the similarity score. Reject just dismisses the row — there's no
/// negative-example storage yet, that's a future curation surface.
struct HeuristicReviewSheet: View {
    let response: Components.Schemas.HeuristicPredictionsResponse
    let dismiss: () -> Void

    @State private var processed: Set<String> = []
    @State private var accepted: Set<String> = []
    @State private var status: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            list
            Divider()
            footer
        }
        .frame(width: 580, height: 480)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Suggested Links")
                    .font(.headline)
                Text("\(response.predictions.count) candidates from embedding similarity (#919 5c)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Done", action: dismiss)
                .keyboardShortcut(.cancelAction)
        }
        .padding()
    }

    private var list: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(Array(response.predictions.enumerated()), id: \.offset) { _, pred in
                    predictionRow(pred)
                }
            }
            .padding()
        }
    }

    private func predictionRow(_ pred: Components.Schemas.HeuristicPredictionItem) -> some View {
        let key = "\(pred.sourceClaimId)→\(pred.targetClaimId)"
        let done = processed.contains(key)
        return HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Similarity \(String(format: "%.2f", pred.similarityScore))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(pred.sourceClaimId)
                    .font(.caption2)
                    .monospaced()
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
                Image(systemName: "arrow.down.right")
                    .foregroundStyle(.secondary)
                Text(pred.targetClaimId)
                    .font(.caption2)
                    .monospaced()
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if done {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else {
                Button("Accept") { Task { await accept(pred, key: key) } }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                Button("Reject") {
                    accepted.remove(key)
                    processed.insert(key)
                    status = "Rejected \(pred.sourceClaimId) ↔ \(pred.targetClaimId)"
                }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding(8)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .opacity(done ? 0.6 : 1)
    }

    private var footer: some View {
        HStack {
            Text(status)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(
                "\(Self.reviewedCount(total: response.predictions.count, processed: processed))/\(response.predictions.count) reviewed · "
                + "\(Int(Self.acceptanceRate(processed: processed, accepted: accepted) * 100))% accepted"
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 6)
    }

    private func accept(_ pred: Components.Schemas.HeuristicPredictionItem, key: String) async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        do {
            _ = try await library.entityService.createClaimLink(
                claimId: pred.sourceClaimId,
                relatedClaimId: pred.targetClaimId,
                relationType: .supports,
                linkQuality: pred.similarityScore,
                evidence: "Heuristic similarity \(String(format: "%.3f", pred.similarityScore))"
            )
            accepted.insert(key)
            processed.insert(key)
            status = "Linked \(pred.sourceClaimId) ↔ \(pred.targetClaimId)"
        } catch {
            status = "Failed: \(error.localizedDescription)"
        }
    }

    static func reviewedCount(total: Int, processed: Set<String>) -> Int {
        min(total, processed.count)
    }

    static func acceptanceRate(processed: Set<String>, accepted: Set<String>) -> Double {
        guard !processed.isEmpty else { return 0 }
        let acceptedCount = accepted.intersection(processed).count
        return Double(acceptedCount) / Double(processed.count)
    }
}

// MARK: - New Entity Sheet (#916)

/// Simple form to create OR edit a KnowledgeEntity — fills the gap
/// where everything in the KG today comes from extractors. Backed by
/// `EntityServiceGenerated.upsertEntity` (create) or `patchEntity`
/// (edit, when `editing` is non-nil). Calls `onCommit` with the
/// new / updated entity so the browser can refresh.
struct NewEntitySheet: View {
    var editing: Components.Schemas.KnowledgeEntity?
    var onCommit: (Components.Schemas.KnowledgeEntity) -> Void

    init(
        editing: Components.Schemas.KnowledgeEntity? = nil,
        onCreated: @escaping (Components.Schemas.KnowledgeEntity) -> Void
    ) {
        self.editing = editing
        self.onCommit = onCreated
        _canonicalName = State(initialValue: editing?.canonicalName ?? "")
        _entityType = State(initialValue: editing?.entityType?.rawValue ?? "person")
        _aliasesText = State(initialValue: (editing?.aliases ?? []).joined(separator: "\n"))
    }

    @Environment(\.dismiss) private var dismiss
    @State private var canonicalName: String
    @State private var entityType: String
    @State private var aliasesText: String
    @State private var isSaving: Bool = false
    @State private var errorText: String?

    private var isEditing: Bool { editing != nil }

    private let kinds: [(key: String, label: String)] = [
        ("person", "Person"),
        ("location", "Place"),
        ("organization", "Organization"),
        ("event", "Event"),
        ("concept", "Concept"),
        ("other", "Other")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(isEditing ? "Edit Entity" : "New Entity").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            Divider()
            form
            Spacer()
            footer
        }
        .frame(width: 420, height: 320)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Canonical name")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("e.g. Eugenio Córdoba", text: $canonicalName)
                .textFieldStyle(.roundedBorder)

            Text("Type")
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker("", selection: $entityType) {
                ForEach(kinds, id: \.key) { kind in
                    Text(kind.label).tag(kind.key)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Text("Aliases (one per line)")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextEditor(text: $aliasesText)
                .frame(minHeight: 60)
                .border(Color.gray.opacity(0.2))
        }
        .padding()
    }

    private var footer: some View {
        HStack {
            if let errorText = errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
            Spacer()
            Button(isEditing ? "Save" : "Create", action: save)
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(canonicalName.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
        }
        .padding()
    }

    private func save() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isSaving = true
        errorText = nil
        let name = canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)
        let aliases = aliasesText
            .split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        Task {
            do {
                let result: Components.Schemas.KnowledgeEntity
                if let editing = editing, let entityId = editing.id {
                    result = try await library.entityService.patchEntity(
                        entityId,
                        canonicalName: name,
                        entityType: entityType,
                        aliases: aliases
                    )
                } else {
                    result = try await library.entityService.upsertEntity(
                        name: name,
                        entityType: entityType,
                        aliases: aliases
                    )
                }
                onCommit(result)
                dismiss()
            } catch {
                errorText = error.localizedDescription
            }
            isSaving = false
        }
    }
}

// MARK: - Previews

#Preview("Browser") {
    OntologyBrowser()
        .frame(width: 600, height: 500)
        .environment(WorkflowExecutionObserver())
        .environment(KGFocusState.shared)
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
// Force-directed graph over entities and their co-occurrence in claims.
//
// Nodes = entities (filtered by `hiddenKinds` upstream), edges = "appear
// together in the same claim" with weight = co-occurrence count. Layout
// is a Coulomb/Hooke simulation that converges in ~4 seconds and then
// freezes — no continued CPU after that. Click within ~18pt of a node to
// select it; the binding flows back to OntologyBrowser so the detail
// pane updates. (#902, partial #889)
// swiftlint:disable identifier_name
// Force-directed physics uses standard short names (i, j, dx, dy, fx, fy)
// for clarity in the math. Re-enabled after the private struct
// definitions at the end of the file.
struct ForceDirectedGraphView: View { // swiftlint:disable:this type_body_length
    let entities: [Components.Schemas.KnowledgeEntity]
    @Binding var selectedEntityId: String?
    @Environment(KGFocusState.self) private var kgFocusState

    // Simulation state lives in a plain (non-observed) reference type so
    // the per-frame physics writes inside the Canvas render closure don't
    // count as "Modifying state during view update" (#1019, related #998).
    // TimelineView still drives the redraw cadence; `graphRevision` is the
    // observed @State that flips the empty-state branch when a load lands.
    @State private var sim = GraphSimulation()
    @State private var graphRevision = 0
    @State private var isLoading = false
    @State private var loadError: String?

    // Viewport state. The simulation runs in fixed centered coordinates;
    // these transforms map sim-space → screen-space. Pinch updates
    // `scale`; drag updates `panOffset`. Gestures use the
    // `inProgress`-style accumulator pattern so updates remain smooth
    // and the final value persists when the gesture ends.
    @SceneStorage("ontology.graph.scale") private var scaleRaw: Double = 1.0
    @SceneStorage("ontology.graph.panX") private var panXRaw: Double = 0
    @SceneStorage("ontology.graph.panY") private var panYRaw: Double = 0
    private var scale: CGFloat {
        get { CGFloat(scaleRaw) }
        nonmutating set { scaleRaw = Double(newValue) }
    }
    @State private var scaleAtGestureStart: CGFloat = 1.0
    private var panOffset: CGSize {
        get { CGSize(width: panXRaw, height: panYRaw) }
        nonmutating set {
            panXRaw = Double(newValue.width)
            panYRaw = Double(newValue.height)
        }
    }
    @State private var panOffsetAtGestureStart: CGSize = .zero

    private let minScale: CGFloat = 0.4
    private let maxScale: CGFloat = 4.0
    private let neighborLimit = 24

    var body: some View {
        ZStack {
            // Read the observed revision so body re-evaluates when a load
            // completes — `sim` itself is a plain class and doesn't notify.
            // `let _ =` (not `_ =`) is required: a bare discard expression
            // isn't a View, but a discard *declaration* is a valid no-op
            // statement inside the @ViewBuilder.
            // swiftlint:disable:next redundant_discardable_let
            let _ = graphRevision
            Color(.controlBackgroundColor)
            if isLoading {
                ProgressView("Loading graph…")
            } else if let err = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(err).font(.caption).foregroundStyle(.secondary)
                }
            } else if sim.nodes.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "circle.grid.3x3")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text("No graph data").font(.subheadline)
                    Text("Entities need shared claims to form edges")
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                GeometryReader { geo in
                    ZStack(alignment: .topLeading) {
                        TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { timeline in
                            Canvas { ctx, size in
                                sim.step(in: size, now: timeline.date)
                                drawEdges(ctx: ctx)
                                drawNodes(ctx: ctx)
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    if value.translation == .zero {
                                        panOffsetAtGestureStart = panOffset
                                    }
                                    panOffset = CGSize(
                                        width: panOffsetAtGestureStart.width + value.translation.width,
                                        height: panOffsetAtGestureStart.height + value.translation.height
                                    )
                                }
                        )
                        .simultaneousGesture(
                            MagnificationGesture()
                                .onChanged { mag in
                                    scale = min(max(scaleAtGestureStart * mag, minScale), maxScale)
                                }
                                .onEnded { _ in scaleAtGestureStart = scale }
                        )
                        .onTapGesture { location in
                            handleTap(at: location, in: geo.size)
                        }

                        legend
                            .padding(8)
                        viewportControls
                            .padding(8)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                }
            }
        }
        .task(id: entitiesKey) { await load() }
    }

    // Small kind→color legend. Compact so it doesn't crowd the canvas
    // but enough to decode the dots without guessing.
    private var legend: some View {
        VStack(alignment: .leading, spacing: 3) {
            legendRow(kind: .person, label: "Person")
            legendRow(kind: .organization, label: "Org")
            legendRow(kind: .location, label: "Place")
            legendRow(kind: .event, label: "Event")
            legendRow(kind: .concept, label: "Concept")
            legendRow(kind: .other, label: "Other")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.controlBackgroundColor).opacity(0.85))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.secondary.opacity(0.3), lineWidth: 0.5)
        )
    }

    private func legendRow(
        kind: Components.Schemas.EntityTypeOutput,
        label: String
    ) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color(for: kind))
                .frame(width: 7, height: 7)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    // Compact zoom/reset controls. Mirrors the PDF zoom toolbar style.
    private var viewportControls: some View {
        HStack(spacing: 4) {
            Button {
                let next = min(scale * 1.25, maxScale)
                scale = next
                scaleAtGestureStart = next
            } label: {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom in")
            Button {
                let next = max(scale / 1.25, minScale)
                scale = next
                scaleAtGestureStart = next
            } label: {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom out")
            Button {
                scale = 1.0
                scaleAtGestureStart = 1.0
                panOffset = .zero
                panOffsetAtGestureStart = .zero
            } label: {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(.plain)
            .help("Reset view")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.controlBackgroundColor).opacity(0.85))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.secondary.opacity(0.3), lineWidth: 0.5)
        )
    }

    /// Re-fetch the neighborhood whenever the focus entity changes OR
    /// the upstream entities list changes (i.e. user changed search /
    /// filter). The neighborhood endpoint is bounded + cached on the
    /// backend so this is cheap (sub-100ms on warm cache per #990).
    private var entitiesKey: String {
        let focus = selectedEntityId ?? entities.compactMap(\.id).first ?? ""
        let signature = entities.count
        return "\(focus):\(signature)"
    }

    // MARK: - Data loading

    @MainActor
    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        // Focus selection: use the bound selectedEntityId; fall back to
        // the first entity in the filtered set so the view has something
        // to render when nothing is selected. With the focus-neighborhood
        // model the global "draw all entities in a circle" is gone —
        // graph mode shows ONE focus + its k-hop neighbors. (#976/#977)
        guard let focusId = selectedEntityId
                ?? entities.compactMap(\.id).first else {
            sim.nodes = []
            sim.edges = []
            graphRevision += 1
            return
        }
        guard let library = LibraryManager.shared.globalLibrary else {
            loadError = "No library"
            return
        }
        do {
            let response = try await library.entityService.fetchNeighborhood(
                entityId: focusId,
                hops: 1,
                limit: neighborLimit,
                rank: "edge_weight"
            )
            sim.rebuild(from: response)
            graphRevision += 1
        } catch {
            loadError = error.localizedDescription
        }
    }

    // MARK: - Drawing

    private func drawEdges(ctx: GraphicsContext) {
        for edge in sim.edges {
            guard let source = sim.nodes.first(where: { $0.id == edge.source }),
                  let target = sim.nodes.first(where: { $0.id == edge.target }) else { continue }
            let from = centered(source.position, in: ctx)
            let dest = centered(target.position, in: ctx)
            guard from.x.isFinite && from.y.isFinite && dest.x.isFinite && dest.y.isFinite else { continue }
            var path = Path()
            path.move(to: from)
            path.addLine(to: dest)
            let alpha = min(0.2 + Double(edge.weight) * 0.08, 0.65)
            let width = min(1.0 + CGFloat(edge.weight - 1) * 0.35, 2.6)
            ctx.stroke(path, with: .color(.secondary.opacity(alpha)), lineWidth: width)
            // Predicate label at the midpoint. Skip when the edge is so
            // short that the label would overlap a node. Background-
            // ribbon the label so it's readable across the line.
            let dx = dest.x - from.x
            let dy = dest.y - from.y
            let lineLen = sqrt(dx * dx + dy * dy)
            if lineLen > 72, edge.weight >= 2, !edge.predicate.isEmpty {
                let midX = (from.x + dest.x) / 2
                let midY = (from.y + dest.y) / 2
                let label = Text(edge.predicate)
                    .font(.caption2)
                    .italic()
                    .foregroundColor(.accentColor)
                ctx.draw(label, at: CGPoint(x: midX, y: midY), anchor: .center)
            }
        }
    }

    private func drawNodes(ctx: GraphicsContext) {
        for node in sim.nodes {
            let pos = centered(node.position, in: ctx)
            guard pos.x.isFinite && pos.y.isFinite else { continue }
            let radius: CGFloat = node.id == selectedEntityId ? 9 : 6
            let circle = Path(ellipseIn: CGRect(
                x: pos.x - radius,
                y: pos.y - radius,
                width: radius * 2,
                height: radius * 2
            ))
            ctx.fill(circle, with: .color(color(for: node.kind)))
            if node.id == selectedEntityId {
                ctx.stroke(circle, with: .color(.accentColor), lineWidth: 2)
            } else {
                ctx.stroke(circle, with: .color(.primary.opacity(0.3)), lineWidth: 0.5)
            }
            let label = Text(node.name).font(.caption2).foregroundColor(.primary)
            ctx.draw(label, at: CGPoint(x: pos.x, y: pos.y + radius + 8), anchor: .top)
        }
    }

    private func centered(_ point: CGPoint, in ctx: GraphicsContext) -> CGPoint {
        // Apply viewport scale + pan around the canvas center, so pinch
        // zooms toward the center and drag moves the whole graph
        // together. Edge widths and node radii intentionally don't scale
        // — keeps the graph readable at any zoom level.
        let bounds = ctx.clipBoundingRect
        return CGPoint(
            x: bounds.midX + point.x * scale + panOffset.width,
            y: bounds.midY + point.y * scale + panOffset.height
        )
    }

    // MARK: - Interaction

    private func handleTap(at location: CGPoint, in size: CGSize) {
        // Inverse of `centered`: back out scale + panOffset to get
        // simulation-space coordinates for hit-testing.
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let local = CGPoint(
            x: (location.x - center.x - panOffset.width) / scale,
            y: (location.y - center.y - panOffset.height) / scale
        )
        // Hit radius is in simulation space — divide by scale so the tap
        // target stays a constant ~18pt of screen space.
        let hitRadius: CGFloat = 18 / scale
        // Node hit-test first — clicking a node refocuses.
        var bestNode: (id: String, dist: CGFloat)?
        for node in sim.nodes {
            let dx = node.position.x - local.x
            let dy = node.position.y - local.y
            let dist = sqrt(dx * dx + dy * dy)
            if dist < hitRadius, dist < (bestNode?.dist ?? .greatestFiniteMagnitude) {
                bestNode = (node.id, dist)
            }
        }
        if let hit = bestNode {
            selectedEntityId = hit.id
            kgFocusState.focusEntity(entityId: hit.id)
            return
        }
        // No node hit — check whether the tap landed near an edge's
        // midpoint (where the predicate label sits). Clicking an edge
        // opens the source claim. (#982 — wireframe Path B)
        let edgeHitRadius: CGFloat = 22 / scale
        var bestEdge: (edge: GraphEdge, dist: CGFloat)?
        for edge in sim.edges {
            guard let source = sim.nodes.first(where: { $0.id == edge.source }),
                  let target = sim.nodes.first(where: { $0.id == edge.target }) else { continue }
            let midX = (source.position.x + target.position.x) / 2
            let midY = (source.position.y + target.position.y) / 2
            let dx = midX - local.x
            let dy = midY - local.y
            let dist = sqrt(dx * dx + dy * dy)
            if dist < edgeHitRadius, dist < (bestEdge?.dist ?? .greatestFiniteMagnitude) {
                bestEdge = (edge, dist)
            }
        }
        if let hit = bestEdge {
            kgFocusState.focusClaim(
                claimId: hit.edge.claimId,
                sourceDocumentId: hit.edge.sourceDocumentId,
                sourcePageLabel: hit.edge.pageLabel
            )
        }
    }

    // MARK: - Colors

    private func color(
        for kind: Components.Schemas.EntityTypeOutput?
    ) -> Color {
        guard let kind else { return .gray }
        switch kind {
        case .person: return .blue
        case .organization: return .purple
        case .location: return .green
        case .event: return .orange
        case .concept: return .yellow
        case .citation: return .brown
        case .other: return .gray
        }
    }
}

@MainActor
private final class OntologyBrowserLoadState: ObservableObject {
    @Published var entities: [Components.Schemas.KnowledgeEntity] = []
    @Published var claimCounts: [String: Int] = [:]
    @Published var loadError: String?
    @Published var isLoading = false
    @Published var entityClaims: [Components.Schemas.KnowledgeClaim] = []
    @Published var isLoadingClaims = false
}

// MARK: - Model

private struct GraphNode: Identifiable {
    let id: String
    let name: String
    let kind: Components.Schemas.EntityTypeOutput?
    var position: CGPoint
    var velocity: CGVector
}

private struct GraphEdge {
    let source: String
    let target: String
    /// SVO predicate verb from the backend (e.g. "served as", "founded").
    /// Drawn mid-edge so the user sees the relationship type at a glance.
    let predicate: String
    /// Claim ID — so click-edge can focus the source without navigating.
    let claimId: String
    /// Source document ID + page label for cross-view KG focus.
    let sourceDocumentId: String
    let pageLabel: String?
    /// Aggregate weight (how many claims connect these two entities).
    /// Used by the render to set line opacity / thickness.
    let weight: Int
}

private struct EdgeKey: Hashable {
    let source: String
    let target: String
}

struct EpistemologyGraphEdgeInput {
    let sourceId: String
    let targetId: String
    let predicate: String
    let claimId: String
    let sourceDocumentId: String
    let sourcePageLabel: String?
}

struct EpistemologyGraphReducedEdge: Equatable {
    let source: String
    let target: String
    let predicate: String
    let claimId: String
    let sourceDocumentId: String
    let pageLabel: String?
    let weight: Int
}

enum EpistemologyGraphReducer {
    static func reduce(
        edges: [EpistemologyGraphEdgeInput],
        allowedNodeIds: Set<String>,
        maxEdges: Int
    ) -> [EpistemologyGraphReducedEdge] {
        var byPair: [EdgeKey: EpistemologyGraphReducedEdge] = [:]
        var weights: [EdgeKey: Int] = [:]
        for edge in edges {
            guard allowedNodeIds.contains(edge.sourceId), allowedNodeIds.contains(edge.targetId) else {
                continue
            }
            let source = min(edge.sourceId, edge.targetId)
            let target = max(edge.sourceId, edge.targetId)
            let key = EdgeKey(source: source, target: target)
            weights[key, default: 0] += 1
            if byPair[key] == nil {
                byPair[key] = EpistemologyGraphReducedEdge(
                    source: edge.sourceId,
                    target: edge.targetId,
                    predicate: edge.predicate,
                    claimId: edge.claimId,
                    sourceDocumentId: edge.sourceDocumentId,
                    pageLabel: edge.sourcePageLabel,
                    weight: 1
                )
            } else if let existing = byPair[key], edge.predicate.count > existing.predicate.count {
                byPair[key] = EpistemologyGraphReducedEdge(
                    source: existing.source,
                    target: existing.target,
                    predicate: edge.predicate,
                    claimId: existing.claimId,
                    sourceDocumentId: existing.sourceDocumentId,
                    pageLabel: existing.pageLabel,
                    weight: 1
                )
            }
        }
        return byPair.compactMap { pair, edge in
            EpistemologyGraphReducedEdge(
                source: edge.source,
                target: edge.target,
                predicate: edge.predicate,
                claimId: edge.claimId,
                sourceDocumentId: edge.sourceDocumentId,
                pageLabel: edge.pageLabel,
                weight: weights[pair] ?? 1
            )
        }
        .sorted { lhs, rhs in
            if lhs.weight == rhs.weight {
                return lhs.predicate.count > rhs.predicate.count
            }
            return lhs.weight > rhs.weight
        }
        .prefix(maxEdges)
        .map { $0 }
    }
}

/// Mutable force-directed simulation state, held as a plain reference type
/// so the per-frame physics writes from inside the `Canvas` render closure
/// don't trip SwiftUI's "Modifying state during view update" check (#1019).
/// The view keeps this in `@State` purely for a stable instance; redraws
/// are driven by `TimelineView`, and the empty-state branch is flipped by
/// a separate observed `graphRevision` counter after each load.
private final class GraphSimulation {
    private let maxNeighbors = 24
    private let maxEdges = 80
    var nodes: [GraphNode] = []
    var edges: [GraphEdge] = []
    private var startTime: Date = .now
    private var lastTick: Date = .now

    /// Lay out the focus at the origin + neighbor entities on a circle
    /// around it. Edges carry the predicate (verb) from the backend.
    func rebuild(from response: Components.Schemas.NeighborhoodResponse) {
        let focusKind = response.focusEntityType
        var newNodes: [GraphNode] = []
        newNodes.append(GraphNode(
            id: response.focusEntityId,
            name: response.focusCanonicalName,
            kind: focusKind.flatMap { Components.Schemas.EntityTypeOutput(rawValue: $0) },
            position: .zero,
            velocity: .zero
        ))
        let neighbors = Array(response.neighbors.prefix(maxNeighbors))
        let count = max(neighbors.count, 1)
        let radius: CGFloat = 220
        for (idx, neighbor) in neighbors.enumerated() {
            let angle = Double(idx) / Double(count) * 2.0 * .pi
            newNodes.append(GraphNode(
                id: neighbor.id,
                name: neighbor.canonicalName,
                kind: neighbor.entityType.flatMap {
                    Components.Schemas.EntityTypeOutput(rawValue: $0)
                },
                position: CGPoint(x: cos(angle) * radius, y: sin(angle) * radius),
                velocity: .zero
            ))
        }
        let nodeIds = Set(newNodes.map(\.id))
        let reduced = EpistemologyGraphReducer.reduce(
            edges: response.edges.map { edge in
                EpistemologyGraphEdgeInput(
                    sourceId: edge.sourceId,
                    targetId: edge.targetId,
                    predicate: edge.predicate,
                    claimId: edge.claimId,
                    sourceDocumentId: edge.sourceDocumentId,
                    sourcePageLabel: edge.sourcePageLabel
                )
            },
            allowedNodeIds: nodeIds,
            maxEdges: maxEdges
        )
        edges = reduced.map { edge in
            GraphEdge(
                source: edge.source,
                target: edge.target,
                predicate: edge.predicate,
                claimId: edge.claimId,
                sourceDocumentId: edge.sourceDocumentId,
                pageLabel: edge.pageLabel,
                weight: edge.weight
            )
        }
        nodes = newNodes
        startTime = .now
        lastTick = .now
    }

    func step(in size: CGSize, now: Date) {
        guard !nodes.isEmpty, size.width > 0, size.height > 0 else { return }
        let elapsed = now.timeIntervalSince(startTime)
        guard elapsed < 4.0 else { return }
        let dt = max(min(now.timeIntervalSince(lastTick), 1.0 / 30.0), 0.001)
        lastTick = now

        let positions = nodes.map(\.position)
        var forces: [CGVector] = Array(repeating: .zero, count: nodes.count)
        applyRepulsion(positions: positions, forces: &forces)
        applySprings(positions: positions, forces: &forces)
        integrate(forces: forces, dt: dt, size: size)
    }

    private func applyRepulsion(positions: [CGPoint], forces: inout [CGVector]) {
        let repulsion: CGFloat = 6000
        for i in 0..<nodes.count {
            for j in (i + 1)..<nodes.count {
                let dx = positions[i].x - positions[j].x
                let dy = positions[i].y - positions[j].y
                let distSq = max(dx * dx + dy * dy, 25)
                let dist = sqrt(distSq)
                let force = repulsion / distSq
                let fx = (dx / dist) * force
                let fy = (dy / dist) * force
                forces[i].dx += fx; forces[i].dy += fy
                forces[j].dx -= fx; forces[j].dy -= fy
            }
        }
    }

    private func applySprings(positions: [CGPoint], forces: inout [CGVector]) {
        let springLength: CGFloat = 110
        let springStiffness: CGFloat = 0.04
        let idIndex: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.enumerated().map { ($1.id, $0) }
        )
        for edge in edges {
            guard let aIdx = idIndex[edge.source],
                  let bIdx = idIndex[edge.target] else { continue }
            let dx = positions[bIdx].x - positions[aIdx].x
            let dy = positions[bIdx].y - positions[aIdx].y
            let dist = max(sqrt(dx * dx + dy * dy), 0.001)
            let force = springStiffness * (dist - springLength)
            let fx = (dx / dist) * force
            let fy = (dy / dist) * force
            forces[aIdx].dx += fx; forces[aIdx].dy += fy
            forces[bIdx].dx -= fx; forces[bIdx].dy -= fy
        }
    }

    private func integrate(forces: [CGVector], dt: TimeInterval, size: CGSize) {
        let damping: CGFloat = 0.82
        let centerPull: CGFloat = 0.012
        let maxSpeed: CGFloat = 240
        let halfW = size.width / 2 - 20
        let halfH = size.height / 2 - 20
        for i in 0..<nodes.count {
            var node = nodes[i]
            var force = forces[i]
            force.dx += -(node.position.x) * centerPull
            force.dy += -(node.position.y) * centerPull
            node.velocity.dx = (node.velocity.dx + force.dx * CGFloat(dt)) * damping
            node.velocity.dy = (node.velocity.dy + force.dy * CGFloat(dt)) * damping
            let speed = sqrt(node.velocity.dx * node.velocity.dx + node.velocity.dy * node.velocity.dy)
            if speed > maxSpeed {
                node.velocity.dx = node.velocity.dx / speed * maxSpeed
                node.velocity.dy = node.velocity.dy / speed * maxSpeed
            }
            guard node.velocity.dx.isFinite, node.velocity.dy.isFinite else {
                node.velocity = .zero
                nodes[i] = node
                continue
            }
            node.position.x += node.velocity.dx * CGFloat(dt)
            node.position.y += node.velocity.dy * CGFloat(dt)
            guard node.position.x.isFinite, node.position.y.isFinite else {
                node.position = .zero
                node.velocity = .zero
                nodes[i] = node
                continue
            }
            node.position.x = min(max(node.position.x, -halfW), halfW)
            node.position.y = min(max(node.position.y, -halfH), halfH)
            nodes[i] = node
        }
    }
}

// swiftlint:enable identifier_name

// MARK: - EntityKindChartView (#902 Charts overlay)

import Charts

/// At-a-glance entity-type distribution. Renders a bar chart of the
/// filteredEntities passed in from OntologyBrowser so toggling the kind
/// filter in the toolbar updates the chart live. Pairs with the same
/// color palette used in `ForceDirectedGraphView` so a glance across
/// modes stays consistent.
struct EntityKindChartView: View {
    let entities: [Components.Schemas.KnowledgeEntity]

    /// One bar per kind. Keeps the canonical order (person → place →
    /// organization → event → concept → other) so the chart's reading
    /// order matches the filter menu and the legend.
    private static let kindOrder: [Components.Schemas.EntityTypeOutput] = [
        .person, .location, .organization, .event, .concept, .other
    ]

    private struct KindCount: Identifiable {
        let kind: Components.Schemas.EntityTypeOutput
        let label: String
        let count: Int
        var id: String { label }
    }

    private var counts: [KindCount] {
        var bucket: [Components.Schemas.EntityTypeOutput: Int] = [:]
        for entity in entities {
            let key = entity.entityType ?? .other
            bucket[key, default: 0] += 1
        }
        return Self.kindOrder.map { kind in
            KindCount(kind: kind, label: Self.label(for: kind), count: bucket[kind] ?? 0)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Entities by kind")
                .font(.headline)
                .foregroundStyle(.primary)
            Text("\(entities.count) entities total")
                .font(.caption)
                .foregroundStyle(.secondary)
            Chart(counts) { row in
                BarMark(
                    x: .value("Count", row.count),
                    y: .value("Kind", row.label)
                )
                .foregroundStyle(color(for: row.kind))
                .annotation(position: .trailing, alignment: .leading) {
                    // `row.count` is an Int (entity count), not a collection
                    // size — empty_count's isEmpty suggestion doesn't apply.
                    // swiftlint:disable:next empty_count
                    if row.count > 0 {
                        Text("\(row.count)")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(preset: .aligned, position: .leading) { _ in
                    AxisValueLabel().font(.caption2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(.controlBackgroundColor))
    }

    private static func label(for kind: Components.Schemas.EntityTypeOutput) -> String {
        switch kind {
        case .person: return "People"
        case .location: return "Places"
        case .organization: return "Organizations"
        case .event: return "Events"
        case .concept: return "Concepts"
        case .citation: return "Citations"
        case .other: return "Other"
        }
    }

    // Mirrors the palette in ForceDirectedGraphView.color(for:) so the
    // colors line up across modes.
    private func color(for kind: Components.Schemas.EntityTypeOutput) -> Color {
        switch kind {
        case .person: return .blue
        case .organization: return .purple
        case .location: return .green
        case .event: return .orange
        case .concept: return .yellow
        case .citation: return .brown
        case .other: return .gray
        }
    }
}
