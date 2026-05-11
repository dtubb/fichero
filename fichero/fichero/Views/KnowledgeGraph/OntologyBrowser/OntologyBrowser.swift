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

    /// Persisted across launches per the KG inspector pattern. Empty
    /// CSV = show every entity kind (default).
    @AppStorage("ontology.browser.hiddenKinds")
    private var hiddenKindsCSV: String = ""

    private var hiddenKinds: Set<String> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .map { String($0) }
                .filter { !$0.isEmpty }
        )
    }

    private func setHidden(_ kind: String, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.sorted().joined(separator: ",")
    }

    /// Entity-type cases shown as filter chips. Matches
    /// `EntityType-Output` schema (person/location/organization/event/
    /// concept/other) — keep the order stable for sidebar muscle memory.
    private let entityKinds: [(String, String, String)] = [
        ("person", "People", "person.2"),
        ("location", "Places", "mappin.circle"),
        ("organization", "Organizations", "building.2"),
        ("event", "Events", "calendar"),
        ("concept", "Concepts", "tag"),
        ("other", "Other", "questionmark.circle")
    ]

    private var filteredEntities: [Components.Schemas.KnowledgeEntity] {
        let hidden = hiddenKinds
        guard !hidden.isEmpty else { return entities }
        return entities.filter { entity in
            let kind = entity.entityType?.rawValue ?? "other"
            return !hidden.contains(kind)
        }
    }

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
            filterChips
            Divider()
            entityList
        }
        .frame(minWidth: 220, maxWidth: 320)
    }

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(entityKinds, id: \.0) { kind, label, icon in
                    let isOn = !hiddenKinds.contains(kind)
                    Button {
                        setHidden(kind, hidden: isOn)
                    } label: {
                        Label(label, systemImage: icon)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                Capsule()
                                    .fill(isOn
                                          ? Color.accentColor.opacity(0.18)
                                          : Color.gray.opacity(0.12))
                            )
                            .foregroundStyle(isOn ? Color.accentColor : .secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isOn ? "Hide \(label.lowercased())" : "Show \(label.lowercased())")
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
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
