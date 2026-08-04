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
            // #4489 ②, now closed. This branch pruned the legacy `entities`
            // mirror and nothing else, so once that container was deleted it
            // did nothing at all: `libraryEntities`, `libraryClaimCounts` and
            // `entitiesByDocumentId` each kept a remotely-deleted entity, while
            // the LOCAL `delete(entityIds:)` pruned all three. Push and local
            // disagreed about what "deleted" means.
            //
            // Both now go through the same seam, so they cannot drift again.
            // An entity deleted in another window disappears here; an event
            // carrying no ids is a no-op inside the seam rather than a
            // special case out here.
            removeEntitiesEverywhere(ids: Set(event.entityIds))
        default:
            break
        }
    }

    var hasDocumentScope: Bool {
        !loadedDocumentIds.isEmpty || lastLoadedDocumentId != nil
    }
}
