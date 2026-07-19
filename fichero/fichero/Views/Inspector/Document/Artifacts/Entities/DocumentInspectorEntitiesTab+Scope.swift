import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Entities Tab: Scope & Grouping
//
// Members here are `internal` (not `private`) where a helper in the core file
// or another `DocumentInspectorEntitiesTab+*.swift` extension references them —
// a same-type extension in a different file cannot see a `private` member.
// `aggregatingChildren` stays `private`: it is only used within this file.

extension DocumentInspectorEntitiesTab {
    var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    func recomputeGrouped() {
        let dict = Dictionary(grouping: scopedEntities) { entity in
            EntityKind(apiType: entity.entityType) ?? .other
        }
        let hidden = hiddenKinds
        grouped = EntityKind.displayOrder.compactMap { kind in
            guard !hidden.contains(kind), let items = dict[kind], !items.isEmpty else {
                return nil
            }
            return (kind, items.sorted { lhs, rhs in
                lhs.canonicalName.localizedCaseInsensitiveCompare(rhs.canonicalName) == .orderedAscending
            })
        }
    }

    var hasActiveKindFilter: Bool {
        !hiddenKinds.isEmpty
    }

    var orderedEntities: [Components.Schemas.KnowledgeEntity] {
        grouped.flatMap(\.1)
    }

    var selectedEntities: [Components.Schemas.KnowledgeEntity] {
        orderedEntities.filter { entitySelection.contains($0.stableInspectorId) }
    }

    var selectedEntity: Components.Schemas.KnowledgeEntity? {
        guard entitySelection.count == 1 else { return nil }
        return selectedEntities.first
    }

    var scopedEntities: [Components.Schemas.KnowledgeEntity] {
        entityStore.entities(forDocument: documentId)
    }

    var isFolder: Bool { document.docType == .folder }

    // `private`: only `loadScopedEntities` (same file) reads this.
    /// Aggregate across children when a folder is inspected and the scope toggle
    /// is on (#3450); otherwise the entities are just this document's.
    private var aggregatingChildren: Bool { isFolder && includeChildren }

    /// Load entities for the current scope: a folder's aggregated children, or a
    /// single document. Published under `documentId`, so `scopedEntities` reads
    /// the right set either way.
    func loadScopedEntities(force: Bool = false) async {
        if aggregatingChildren {
            let childIds = await documentStore.children(of: documentId).map(\.id)
            await entityStore.loadAggregatedEntities(
                forFolder: documentId,
                childDocumentIds: childIds,
                force: force
            )
        } else {
            await entityStore.loadEntities(forDocument: documentId, force: force)
        }
    }

    var scopedLoadError: String? {
        entityStore.loadError(forDocument: documentId)
    }

    var isScopedLoading: Bool {
        entityStore.isLoading(forDocument: documentId)
    }

    var bulkActionScopeLabel: String {
        document.docType == .page ? "This page only" : "This folder only"
    }
}
