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
    @Binding var selection: Set<String>
    /// Focus the entity + open its detail/editor — supplied by LibraryView, which
    /// owns the KG focus state and the detail binding.
    let onOpen: (Components.Schemas.KnowledgeEntity) -> Void

    @Environment(EntityStore.self) private var store

    var body: some View {
        EntitiesTableView(
            items: items,
            selection: $selection,
            isLoading: store.isLoadingLibrary,
            emptyMessage: emptyMessage,
            actions: actions
        )
        // A high limit: we filter to the folder client-side, so the library-wide
        // list must be complete enough not to drop the folder's entities (the
        // default page size is small). The store dedups repeat loads.
        .task { await store.loadEntities(limit: 1000) }
    }

    private var emptyMessage: String {
        if let error = store.libraryLoadError {
            return "Couldn't load entities: \(error)"
        }
        return folderDocumentIds == nil
            ? "No entities in this library yet. Run knowledge extraction to populate them."
            : "No entities in this folder yet."
    }

    /// Library entities, folder-scoped client-side, as sortable rows. Claim counts
    /// come from the store's already-loaded map.
    private var items: [EntitiesTableView.Item] {
        let docsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return store.libraryEntities.compactMap { entity -> EntitiesTableView.Item? in
            if let scope = folderDocumentIds {
                let sources = Set(entity.sourceDocumentIds ?? [])
                guard !sources.isDisjoint(with: scope) else { return nil }
            }
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
