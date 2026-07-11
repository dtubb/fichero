import FicheroAPIClient
import SwiftUI

// Entity list sidebar, search bar, list rows, and navigation for
// OntologyBrowser (#1703).
extension OntologyBrowser {
    static let entityListLimit = 100

    // MARK: - Entity List Sidebar

    static func truncationMessage(
        entityCount: Int,
        searchText: String,
        limit: Int = entityListLimit
    ) -> String? {
        guard entityCount >= limit else { return nil }
        if searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Showing the first \(limit) entities. Refine the list to narrow the graph."
        }
        return "Showing the first \(limit) matching entities. Refine the search to narrow the list."
    }

    var entityTruncationMessage: String? {
        Self.truncationMessage(entityCount: entities.count, searchText: searchText)
    }

    var entityListSidebar: some View {
        VStack(spacing: 0) {
            searchBar
            if let entityTruncationMessage {
                Divider()
                Text(entityTruncationMessage)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
            }
            Divider()
            entityList
                .frame(maxWidth: .infinity)  // fill the column, don't anchor left (#981)
        }
    }

    var searchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)

            TextField("Search entities...", text: Binding(
                get: { searchText },
                set: { searchText = $0 }
            ))
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

    var entityList: some View {
        List(selection: Binding(
            get: { selectedEntityId },
            set: { selectedEntityId = $0 }
        )) {
            entityListContent
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

    @ViewBuilder
    private var entityListContent: some View {
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
            emptyEntityListState
        } else {
            ForEach(nonDateEntities, id: \.id) { entity in
                entityRow(entity)
            }
            if !dateEntities.isEmpty {
                dateBucketSection
            }
        }
    }

    private var emptyEntityListState: some View {
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
    }

    private var dateBucketSection: some View {
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

    /// Open an entity in a new tab/window (#1685). Reuses the Safari
    /// new-window path; the cross-window `KGFocusState` singleton carries the
    /// focus so the destination OntologyBrowser selects this entity.
    func openEntityInNewWindow(_ entity: Components.Schemas.KnowledgeEntity, asTab: Bool) {
        guard let entityId = entity.id else { return }
        // Follow-up (#1685): the new window's OntologyBrowser only reacts to
        // focusedEntityId via .onChange, so a brand-new window that mounts
        // after this assignment may not auto-select. A one-shot on-appear
        // consumer of KGFocusState would make this deterministic.
        kgFocusState.focusEntity(entityId: entityId)
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, asTab: asTab, using: openWindow)
    }

    func entityRow(_ entity: Components.Schemas.KnowledgeEntity) -> some View {
        EntityRow(entity: entity, claimCount: claimCounts[entity.id ?? ""] ?? 0)
            .tag(entity.id)
            .contextMenu {
                OpenInMenuItems(
                    open: { selectedEntityId = entity.id },
                    openInNewTab: { openEntityInNewWindow(entity, asTab: true) },
                    openInNewWindow: { openEntityInNewWindow(entity, asTab: false) }
                )
                Divider()
                Button("Edit entity…") { entityPendingEdit = entity }
                Button("Merge entities…") { entityPendingMerge = entity }
                Button("Split entity…") { entityPendingSplit = entity }
                Divider()
                Button("Delete entity…", role: .destructive) {
                    entityPendingDeletion = entity
                }
            }
    }

    func applyHistoryEntry(_ entry: NavigationHistoryManager.Entry?) {
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

    func loadEntities() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            async let entityList = service.listEntities(limit: Self.entityListLimit)
            async let counts = service.fetchClaimCounts()
            entities = try await entityList
            claimCounts = (try? await counts) ?? [:]
        } catch {
            loadError = error.localizedDescription
        }

        isLoading = false
    }

    func searchEntities() async {
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
            entities = try await service.listEntities(query: searchText, limit: Self.entityListLimit)
        } catch {
            await loadEntities()
        }

        isLoading = false
    }
}
