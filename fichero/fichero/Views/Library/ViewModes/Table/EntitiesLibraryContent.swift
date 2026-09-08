import FicheroAPIClient
import SwiftUI

// MARK: - Entities library content (folder-scoped entities as a table)

/// Hosts the entities table inside the library: loads library-wide entities via
/// the shared `EntityStore`, folder-scopes them client-side, and wires the row
/// context menu to the EXISTING curation services (bless / reject / retype /
/// merge / delete). Shows ALL entities — duplicates and messy NER included —
/// because the demo point is that they are visible AND curatable in place.
struct EntitiesLibraryContent: View {
    /// The folder's document ids for client-side scoping; `nil` is library-wide
    /// (the Phase-3 sidebar path). `/api/entities` has no recursive scope, so we
    /// filter the library-wide list by the entity's `source_document_ids`.
    let folderDocumentIds: Set<String>?
    /// The loaded documents, to resolve an entity's node parent and its open
    /// target to a real document.
    let documents: [Document]
    /// The library's active ⌘F query, so the entities table narrows with the same
    /// search box — and so a search that matched only entities can auto-surface
    /// the matching ones (E: "if there's stuff to show, show it").
    var searchQuery: String? = nil
    @Binding var selection: Set<String>
    /// Focus the entity + open its detail/editor — supplied by LibraryView, which
    /// owns the KG focus state and the detail binding.
    let onOpen: (Components.Schemas.KnowledgeEntity) -> Void

    @Environment(EntityStore.self) private var store

    /// Per-table filter (spec: kg-tables, filter.text / filter.entity-type). Intersects
    /// with the shared ⌘F `searchQuery`; empty text + nil type = no per-table filter.
    @State private var filterText = ""
    @State private var filterType: String?

    /// Presents the manual-create sheet (spec: kg-tables `entity.create`). A researcher
    /// hand-authors an entity, not only curating AI output. Reuses the existing
    /// `NewEntitySheet` (create/edit) rather than a parallel form.
    @State private var showingCreateSheet = false

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            EntitiesTableView(
                items: items,
                selection: $selection,
                isLoading: store.isLoadingLibrary,
                emptyMessage: emptyMessage,
                actions: actions
            )
        }
        // A high limit: we filter to the folder client-side, so the library-wide
        // list must be complete enough not to drop the folder's entities (the
        // default page size is small). The store dedups repeat loads.
        .task { await store.loadEntities(limit: 25000) }
        .sheet(isPresented: $showingCreateSheet) {
            // Reuse the Ontology create/edit sheet; it reads its own EntityService
            // from the environment (the library it mutates). On commit, force a
            // library-wide reload so the new row appears here and select it.
            NewEntitySheet(onCreated: handleCreatedEntity)
        }
    }

    /// After a manual create, force-reload the library-wide list (the change-stream's
    /// scheduleReload targets the document scope; the table reads `libraryEntities`)
    /// and select the new row so the researcher lands on what they just made.
    private func handleCreatedEntity(_ entity: Components.Schemas.KnowledgeEntity) {
        guard entity.id != nil else { return }
        Task {
            await store.loadEntities(limit: 25000, force: true)
            let parent = Document(id: entity.sourceDocumentIds?.first ?? "unknown",
                                  name: entity.canonicalName)
            selection = [LibraryOutlineNode.entityItem(entity, parent: parent).id]
        }
    }

    /// Whether an entity row survives the combined filter — the shared search AND
    /// the per-table text AND the type picker must all pass (intersection). Pure so
    /// the rule is testable without a rendered table. (spec: kg-tables,
    /// filter.combines-with-search)
    static func entityMatches(
        name: String,
        type: String,
        search: String?,
        filterText: String,
        filterType: String?
    ) -> Bool {
        let haystack = "\(name) \(type)".lowercased()
        if let search, !search.isEmpty, !haystack.contains(search.lowercased()) { return false }
        let text = filterText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !text.isEmpty, !haystack.contains(text) { return false }
        if let filterType, !filterType.isEmpty,
           type.lowercased() != filterType.lowercased() { return false }
        return true
    }

    /// The entity types present in the loaded set, for the type picker (only offer
    /// types that exist — filter.entity-type).
    private var availableTypes: [String] {
        Array(Set(store.libraryEntities.compactMap { $0.entityType?.rawValue })).sorted()
    }

    @ViewBuilder
    private var filterBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .foregroundStyle(.secondary)
            TextField("Filter entities", text: $filterText)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 220)
            Menu {
                Button("All types") { filterType = nil }
                Divider()
                ForEach(availableTypes, id: \.self) { type in
                    Button(type.capitalized) { filterType = type }
                }
            } label: {
                Label(filterType?.capitalized ?? "All types", systemImage: "tag")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            Spacer()
            // Manual create (spec: kg-tables `entity.create`) — hand-author an entity
            // from the table, not only via the Ontology sheet.
            Button {
                showingCreateSheet = true
            } label: {
                Label("New Entity", systemImage: "plus")
            }
            .help("Create an entity by hand")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    private var emptyMessage: String {
        if let error = store.libraryLoadError {
            return "Couldn't load entities: \(error)"
        }
        if let query = trimmedQuery, filterText.isEmpty, filterType == nil {
            return "No entities match “\(query)”."
        }
        if trimmedQuery != nil || !filterText.isEmpty || filterType != nil {
            return "No entities match the current filter."
        }
        return folderDocumentIds == nil
            ? "No entities in this library yet. Run knowledge extraction to populate them."
            : "No entities in this folder yet."
    }

    /// Library entities, folder-scoped client-side, as sortable rows. Claim counts
    /// come from the store's already-loaded map.
    private var trimmedQuery: String? {
        let trimmed = (searchQuery ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private var items: [EntitiesTableView.Item] {
        let docsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return store.libraryEntities.compactMap { entity -> EntitiesTableView.Item? in
            if let scope = folderDocumentIds {
                let sources = Set(entity.sourceDocumentIds ?? [])
                guard !sources.isDisjoint(with: scope) else { return nil }
            }
            guard Self.entityMatches(
                name: entity.canonicalName,
                type: entity.entityType?.rawValue ?? "",
                search: trimmedQuery,
                filterText: filterText,
                filterType: filterType
            ) else { return nil }
            let claimCount = entity.id.flatMap { store.libraryClaimCounts[$0] } ?? 0
            let firstSource = entity.sourceDocumentIds?.first
            let parent = firstSource.flatMap { docsById[$0] }
                ?? Document(id: firstSource ?? "unknown", name: entity.canonicalName)
            return EntitiesTableView.Item(
                node: LibraryOutlineNode.entityItem(entity, parent: parent),
                entity: entity,
                values: EntityTableRow(entity, claimCount: claimCount)
            )
        }
    }

    /// The curation actions, backed 1:1 by existing EntityStore mutations — no new
    /// service. Each is fire-and-forget with the store patching its rows in place,
    /// so the table updates reactively.
    private var actions: EntitiesTableView.Actions {
        EntitiesTableView.Actions(
            open: onOpen,
            setCuration: { entities, curation in
                let ids = entities.compactMap(\.id)
                guard let state = Self.curationState(for: curation) else { return }
                Task { try? await store.setCuration(entityIds: ids, to: state) }
            },
            setType: { entities, rawType in
                Task {
                    for id in entities.compactMap(\.id) {
                        try? await store.reclassify(entityId: id, to: rawType)
                    }
                }
            },
            merge: { entities in
                // Keep the richest row as the survivor — the one carrying the most
                // claims is the least surprising thing to absorb the others into.
                let ranked = entities.compactMap(\.id).sorted {
                    (store.libraryClaimCounts[$0] ?? 0) > (store.libraryClaimCounts[$1] ?? 0)
                }
                guard let survivor = ranked.first, ranked.count >= 2 else { return }
                let absorbed = Array(ranked.dropFirst())
                Task { try? await store.merge(absorbedIds: absorbed, into: survivor) }
            },
            delete: { entities in
                let ids = entities.compactMap(\.id)
                Task { try? await store.delete(entityIds: ids) }
            }
        )
    }

    /// Map the table's display curation to the entity curation enum. `.merged` is
    /// not a manual action (it's a side effect of merge), so it maps to nil.
    static func curationState(
        for curation: EntityTableRow.Curation
    ) -> Components.Schemas.EntityCurationState? {
        switch curation {
        case .blessed: return .verified
        case .rejected: return .rejected
        case .unreviewed: return .unreviewed
        case .merged: return nil
        }
    }
}
