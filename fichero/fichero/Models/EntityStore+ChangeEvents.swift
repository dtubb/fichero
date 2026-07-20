import Foundation

extension EntityStore {
    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "entity" }

    func apply(_ event: ChangeEvent) {
        switch event.verb {
        case "updated", "merged", "created":
            // Targeted patch isn't cheap to reconstruct from ids alone; reload
            // the current document scope (cheap, document-scoped query).
            scheduleReload()
        case "deleted":
            let deleted = Set(event.entityIds)
            entities.removeAll { entity in
                guard let id = entity.id else { return false }
                return deleted.contains(id)
            }
        default:
            break
        }
    }

    func syncLegacyScope(documentId: String) {
        entities = entitiesByDocumentId[documentId] ?? []
        isLoading = loadingDocumentIds.contains(documentId)
        loadError = loadErrorsByDocumentId[documentId]
    }

    var hasDocumentScope: Bool {
        !loadedDocumentIds.isEmpty || lastLoadedDocumentId != nil
    }
}
