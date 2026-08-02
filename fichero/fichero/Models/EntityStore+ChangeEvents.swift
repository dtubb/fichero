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
            // #4489 ②: this branch pruned the legacy `entities` mirror and
            // nothing else, so it was already invisible — that container had
            // no readers. Removing it does not change behaviour; it makes the
            // gap legible. `libraryEntities`, `libraryClaimCounts` and
            // `entitiesByDocumentId` all still keep a remotely-deleted entity,
            // while the LOCAL `delete(entityIds:)` prunes all three.
            //
            // Deliberately left as-is rather than fixed here: making push and
            // local agree is the seam's job, and doing it in a deletion commit
            // would smuggle a behaviour change into a no-op.
            break
        default:
            break
        }
    }

    var hasDocumentScope: Bool {
        !loadedDocumentIds.isEmpty || lastLoadedDocumentId != nil
    }
}
