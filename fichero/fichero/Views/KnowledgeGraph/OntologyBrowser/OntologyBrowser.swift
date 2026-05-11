import FicheroAPIClient
import SwiftUI

/// Browser panel for exploring entities and their associated claims.
/// Wires #498 — per-library Knowledge Graph view, peer to Workflows
/// and Activity. Uses `EntityServiceGenerated` (\`/api/entities\` +
/// \`/api/claims\`).
struct OntologyBrowser: View {
    @State private var selectedEntityId: String?
    @State private var searchText = ""
    @State private var isSearching = false

    /// Shared with the document-inspector KG tab (`inspector.kg.hiddenKinds`)
    /// so toggling a kind in one place updates the other. #887. Empty
    /// CSV = show every entity kind (default).
    @AppStorage("inspector.kg.hiddenKinds")
    private var hiddenKindsCSV: String = ""

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
        Self.filterEntities(entities, hidden: hiddenKinds)
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            HSplitView {
                entityListSidebar
                entityDetailPanel
            }
        }
        .frame(minWidth: 300, minHeight: 200)
    }

    // MARK: - Top Toolbar (matches MiniToolbar pattern used elsewhere)

    private var toolbar: some View {
        MiniToolbar {
            Image(systemName: "circle.hexagongrid")
                .foregroundStyle(.secondary)
            Text("Knowledge Graph")
                .font(.headline)
                .foregroundStyle(.primary)
            Spacer(minLength: 0)
            filterMenu
            Button {
                Task { await loadEntities() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload entities")
        }
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

    private var entityListSidebar: some View {
        VStack(spacing: 0) {
            searchBar
            Divider()
            entityList
        }
        .frame(minWidth: 220, maxWidth: 320)
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

    @State private var entities: [Components.Schemas.KnowledgeEntity] = []
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
                ForEach(filteredEntities, id: \.id) { entity in
                    EntityRow(entity: entity)
                        .tag(entity.id)
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
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
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

    @State private var entityClaims: [Components.Schemas.KnowledgeClaim] = []
    @State private var isLoadingClaims = false

    private var entityDetailPanel: some View {
        Group {
            if let entityId = selectedEntityId,
               let entity = entities.first(where: { $0.id == entityId }) {
                EntityDetailView(
                    entity: entity,
                    claims: entityClaims,
                    isLoadingClaims: isLoadingClaims
                )
                .task {
                    await loadEntityClaims(id: entityId)
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

    private func loadEntityClaims(id: String) async {
        isLoadingClaims = true

        do {
            let library = LibraryManager.shared.globalLibrary!
            let service = library.entityService
            // listClaims(entityId:) filters /api/claims by entity.
            entityClaims = try await service.listClaims(entityId: id, limit: 50)
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
