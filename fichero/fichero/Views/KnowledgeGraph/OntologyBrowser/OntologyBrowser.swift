import FicheroAPIClient
import SwiftUI

/// Browser panel for exploring entities and their associated claims
struct OntologyBrowser: View {
    @State private var selectedEntityId: String?
    @State private var searchText = ""
    @State private var isSearching = false

    var body: some View {
        HSplitView {
            entityListSidebar
            entityDetailPanel
        }
        .frame(minWidth: 300, minHeight: 200)
    }

    // MARK: - Entity List Sidebar

    private var entityListSidebar: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            entityList
        }
        .frame(minWidth: 200, maxWidth: 300)
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

    @State private var entities: [Components.Schemas.EntityCoreference] = []
    @State private var loadError: String?
    @State private var isLoading = false

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
            } else if entities.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "person.2")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text("No Entities")
                        .font(.subheadline)
                    Text("Entities will appear as you create claims")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .listRowBackground(Color.clear)
            } else {
                ForEach(entities, id: \.entityId) { entity in
                    EntityRow(entity: entity)
                        .tag(entity.entityId)
                }
            }
        }
        .listStyle(.sidebar)
        .task {
            await loadEntities()
        }
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            entities = try await service.listEntities(limit: 100)
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
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            let resolved = try await service.resolveEntity(value: searchText)
            entities = [resolved]
        } catch {
            // Fall back to listing all entities
            await loadEntities()
        }

        isLoading = false
    }

    // MARK: - Entity Detail Panel

    @State private var entityClaims: [Components.Schemas.KnowledgeClaim] = []
    @State private var isLoadingClaims = false

    private var entityDetailPanel: some View {
        Group {
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.entityId == entityId }) {
                EntityDetailView(
                    entity: entity,
                    claims: entityClaims,
                    isLoadingClaims: isLoadingClaims
                )
                .task {
                    await loadEntityClaims(entityId: entityId)
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

    private func loadEntityClaims(entityId: String) async {
        isLoadingClaims = true

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            entityClaims = try await service.filterClaims(entityIds: [entityId], limit: 50)
        } catch {
            entityClaims = []
        }

        isLoadingClaims = false
    }
}

// MARK: - Previews

#Preview("Browser") {
    OntologyBrowser()
        .frame(width: 600, height: 500)
}

#Preview("Entity Row") {
    List {
        EntityRow(entity: Components.Schemas.EntityCoreference(
            entityId: "entity-1",
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
