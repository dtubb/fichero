import FicheroAPIClient
import SwiftUI

// MARK: - Entities library content (folder-scoped entities as a table)

/// Hosts the entities table inside the library: loads this scope's entities
/// via the shared `EntityStore` (#4885: folder-scoped, the SAME server-
/// recursive aggregated seam the Inspector uses; library-wide otherwise) and
/// wires the row context menu to the EXISTING curation services (bless /
/// reject / retype / merge / delete). Shows ALL entities — duplicates and
/// messy NER included — because the demo point is that they are visible AND
/// curatable in place.
struct EntitiesLibraryContent: View {
    /// The folder's OWN id, for the server-recursive aggregated load; `nil` is
    /// library-wide (the Phase-3 sidebar path).
    ///
    /// #4885 (spec: kg-tables, `kg.tables.folder-scope-misses-subfolders`):
    /// this REPLACES the old `folderDocumentIds: Set<String>?` — a client-side
    /// filter of the library-wide list by DIRECT children only, which missed
    /// every entity whose source lived in a SUBFOLDER. The Inspector's own
    /// `DocumentInspectorEntitiesTab+Scope.swift` already solves this via
    /// `EntityStore.loadAggregatedEntities(forFolder:childDocumentIds:)` →
    /// `entities(forDocument:)` — the SAME seam this table now uses, not a
    /// second definition of "this folder's knowledge." No descendant ids are
    /// collected client-side beyond the folder's own DIRECT children (which
    /// `loadAggregatedEntities` already asks for); the recursion itself is
    /// server-side, via `GET /api/documents/{id}/inspector`, which recurses
    /// unconditionally for any document id — no flag needed.
    let folderId: String?
    /// The loaded documents, to resolve an entity's node parent and its open
    /// target to a real document.
    let documents: [Document]
    /// The library's active ⌘F query, so the entities table narrows with the same
    /// search box — and so a search that matched only entities can auto-surface
    /// the matching ones (E: "if there's stuff to show, show it").
    var searchQuery: String?
    @Binding var selection: Set<String>
    /// Focus the entity + open its detail/editor — supplied by LibraryView, which
    /// owns the KG focus state and the detail binding.
    let onOpen: (Components.Schemas.KnowledgeEntity) -> Void
    /// Reports the row ids currently on screen (post-filter) so `LibraryView`'s
    /// ⌘A — the ONE owner of Select All (`LibraryMenuParityTests.
    /// selectAllHasOneOwner`) — can select what this table is actually
    /// showing, never a second handler (#4851/#4794, spec: kg-tables
    /// `kg.view.keyboard-delete`; same `onVisibleIds` shape
    /// `DatasetModeView` already reports through).
    var onVisibleIds: (([String]) -> Void)?

    @Environment(EntityStore.self) private var store

    /// Per-table filter (spec: kg-tables, filter.text / filter.entity-type). Intersects
    /// with the shared ⌘F `searchQuery`; empty text + nil type = no per-table filter.
    @State private var filterText = ""
    @State private var filterType: String?

    /// Presents the manual-create sheet (spec: kg-tables `entity.create`). A researcher
    /// hand-authors an entity, not only curating AI output. Reuses the existing
    /// `NewEntitySheet` (create/edit) rather than a parallel form.
    @State private var showingCreateSheet = false

    /// The entity being edited (spec: kg-tables entity edit-from-table). Presents the
    /// same `NewEntitySheet` in its editing mode. A tiny Identifiable wrapper is needed
    /// because `KnowledgeEntity.id` is optional, which `.sheet(item:)` cannot key on.
    @State private var entityToEdit: Components.Schemas.KnowledgeEntity?

    private struct EditingEntity: Identifiable {
        let entity: Components.Schemas.KnowledgeEntity
        var id: String { entity.id ?? entity.canonicalName }
    }

    var body: some View {
        VStack(spacing: 0) {
            EntitiesTableView(
                items: items,
                selection: $selection,
                isLoading: isLoadingCurrentScope,
                emptyMessage: emptyMessage,
                actions: actions
            )
            // #4850: the filter bar belongs at the BOTTOM, matching the
            // Library pane's own filter (`MiniToolbarPlacement.
            // preferredForReader` — "bottom of library and reader is where
            // we can filter"). Was first in this VStack (top).
            filterBar
        }
        // A high limit: we filter to the folder client-side, so the library-wide
        // list must be complete enough not to drop the folder's entities (the
        // default page size is small). The store dedups repeat loads.
        //
        // Keyed on the store's identity so a LIBRARY SWITCH re-triggers the load:
        // `EntityStore` is per-library and swaps in the environment on a switch
        // (LibraryWorkspaceRoot swaps stores without remounting), but a bare
        // `.task` fires once for the view's lifetime and would NOT refire when
        // the environment store changes — leaving the new library's table
        // un-loaded. The parallel of the Claims F5 fix, so both tables behave
        // identically (spec: panes-workspaces F5 / entities==claims).
        // #4885: folder-scoped, this loads via the SAME aggregated seam the
        // Inspector uses (server-recursive, one document id) — never the
        // library-wide list. Keyed on the folder id too, so switching
        // folders (not just libraries) refires the load.
        .task(id: "\(ObjectIdentifier(store))|\(folderId ?? "")") { await reloadScope(force: false) }
        .sheet(isPresented: $showingCreateSheet) {
            // Reuse the Ontology create/edit sheet; it reads its own EntityService
            // from the environment (the library it mutates). On commit, force a
            // reload of THIS scope so the new row appears here and select it.
            NewEntitySheet(onCreated: handleCreatedEntity)
        }
        .sheet(item: Binding(
            get: { entityToEdit.map(EditingEntity.init) },
            set: { entityToEdit = $0?.entity }
        )) { wrapped in
            // Same sheet, editing mode. On save, force-reload so the edited row
            // reflects the change in place.
            NewEntitySheet(editing: wrapped.entity) { _ in
                entityToEdit = nil
                Task { await reloadScope(force: true) }
            }
        }
        // #4851/#4794: report the visible ids on every input that can change
        // them — the filter inputs directly, and the store's own load
        // finishing (covers the initial load and a library switch). Mirrors
        // `DatasetModeView.reportVisible()`'s trigger set.
        .onChange(of: items.map(\.id)) { _, newIds in onVisibleIds?(newIds) }
        .onChange(of: filterText) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: filterType) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: searchQuery) { _, _ in onVisibleIds?(items.map(\.id)) }
        .onChange(of: isLoadingCurrentScope) { _, loading in
            if !loading { onVisibleIds?(items.map(\.id)) }
        }
    }

    /// True while THIS view's actual scope (folder-aggregated or
    /// library-wide) is loading — not always `store.isLoadingLibrary`,
    /// which is a different scope for a folder-scoped table (#4885).
    private var isLoadingCurrentScope: Bool {
        folderId.map(store.isLoading(forDocument:)) ?? store.isLoadingLibrary
    }

    /// Reload THIS view's scope — the folder's aggregated entities, or the
    /// library-wide list — never the wrong one (#4885: a folder-scoped table
    /// force-reloading the LIBRARY list left its own rows stale).
    private func reloadScope(force: Bool) async {
        if let folderId {
            await store.loadAggregatedEntities(
                forFolder: folderId, childDocumentIds: documents.map(\.id), force: force
            )
        } else {
            await store.loadEntities(limit: 25000, force: force)
        }
    }

    /// After a manual create, force-reload THIS view's actual scope (#4885:
    /// folder-aggregated or library-wide, never the wrong one) and select
    /// the new row so the researcher lands on what they just made.
    private func handleCreatedEntity(_ entity: Components.Schemas.KnowledgeEntity) {
        guard entity.id != nil else { return }
        Task {
            await reloadScope(force: true)
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

    /// This view's actual entity set BEFORE the text/type filter — the
    /// folder's aggregated (server-recursive) entities, or the library-wide
    /// list (#4885: no more client-side direct-children filtering).
    private var scopedEntities: [Components.Schemas.KnowledgeEntity] {
        folderId.map(store.entities(forDocument:)) ?? store.libraryEntities
    }

    /// The entity types present in the loaded set, for the type picker (only offer
    /// types that exist — filter.entity-type).
    private var availableTypes: [String] {
        Array(Set(scopedEntities.compactMap { $0.entityType?.rawValue })).sorted()
    }

    @ViewBuilder
    private var filterBar: some View {
        // Reuses the shared bottom-toolbar-strip component (#4362) instead of
        // a hand-placed HStack, matching the Library pane's own filter chrome.
        PaneFilterBar(placement: .bottom) {
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
            .accessibilityIdentifier("kg.entity.new")
        }
    }

    private var emptyMessage: String {
        let loadError = folderId.map(store.loadError(forDocument:)) ?? store.libraryLoadError
        if let loadError {
            return "Couldn't load entities: \(loadError)"
        }
        if let query = trimmedQuery, filterText.isEmpty, filterType == nil {
            return "No entities match “\(query)”."
        }
        if trimmedQuery != nil || !filterText.isEmpty || filterType != nil {
            return "No entities match the current filter."
        }
        return folderId == nil
            ? "No entities in this library yet. Run knowledge extraction to populate them."
            : "No entities in this folder yet."
    }

    /// This scope's entities (folder-aggregated or library-wide — #4885), as
    /// sortable rows. Claim counts come from the store's already-loaded map.
    private var trimmedQuery: String? {
        let trimmed = (searchQuery ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private var items: [EntitiesTableView.Item] {
        let docsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return scopedEntities.compactMap { entity -> EntitiesTableView.Item? in
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
            edit: { entity in entityToEdit = entity },
            rename: { entity, newName in
                guard let id = entity.id else { return }
                Task { try? await store.rename(entityId: id, to: newName) }
            },
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
