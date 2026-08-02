import FicheroAPIClient
import Foundation
import OSLog

extension EntityStore {
    // MARK: - Load (the store, not the view, owns fetching)

    /// Load the library-wide ontology browser list. Document inspector panes
    /// use `loadEntities(forDocument:)`; this is the same store-backed pattern
    /// for the Knowledge Graph browser.
    func loadEntities(query: String? = nil, limit: Int = 100, force: Bool = false) async {
        let trimmedQuery = query?.trimmingCharacters(in: .whitespacesAndNewlines)
        let searchQuery = trimmedQuery?.isEmpty == false ? trimmedQuery : nil
        if !force, !libraryEntities.isEmpty, libraryLoadError == nil, searchQuery == lastLibraryQuery { return }

        isLoadingLibrary = true
        libraryLoadError = nil
        defer { isLoadingLibrary = false }

        do {
            async let loadedEntities = entityService.listEntities(query: searchQuery, limit: limit)
            async let loadedCounts = entityService.fetchClaimCounts()
            libraryEntities = try await loadedEntities
            libraryClaimCounts = (try? await loadedCounts) ?? [:]
            lastLibraryQuery = searchQuery
        } catch {
            if error.isCancellationError {
                // Superseded by a newer search/load.
                return
            }
            libraryEntities = []
            libraryLoadError = "Couldn't load entities: \(error.localizedDescription)"
        }
    }

    /// Load the inspector entities for `documentId`. Idempotent: re-loading the
    /// same already-populated scope is a no-op unless `force` is set (reload
    /// button / post-mutation refresh).
    func loadEntities(forDocument documentId: String, force: Bool = false) async {
        if !force, loadedDocumentIds.contains(documentId), loadErrorsByDocumentId[documentId] == nil {
            return
        }

        lastLoadedDocumentId = documentId
        loadingDocumentIds.insert(documentId)
        loadErrorsByDocumentId[documentId] = nil
        defer {
            loadingDocumentIds.remove(documentId)
        }
        do {
            let loaded = try await entityService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
            entitiesByDocumentId[documentId] = loaded
            loadErrorsByDocumentId.removeValue(forKey: documentId)
            loadedDocumentIds.insert(documentId)
            log.debug(
                "Loaded \(loaded.count, privacy: .public) entities for \(documentId, privacy: .public)"
            )
        } catch {
            if error.isCancellationError {
                // Superseded by a newer document selection — keep current state.
                return
            }
            entitiesByDocumentId[documentId] = []
            loadErrorsByDocumentId[documentId] = "Couldn't load entities: \(error.localizedDescription)"
            loadedDocumentIds.remove(documentId)
            log.error(
                "Failed to load entities for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    /// Aggregate entities across a folder's children in memory (#3450). Fetches
    /// the folder's own inspector entities plus each child's and unions them by
    /// stable identity, so the folder view can review/filter/merge/split/delete
    /// across children. Published under the folder's own id scope, so
    /// `entities(forDocument: folderId)` returns the aggregate and the list
    /// updates in place (stable ids, no wholesale re-render).
    ///
    /// Client-side: fine for review-scale folders. A server-side aggregation
    /// endpoint is the scale path — see the deferred successor noted on #3450.
    func loadAggregatedEntities(
        forFolder folderId: String,
        childDocumentIds: [String],
        force: Bool = false
    ) async {
        if !force, loadedDocumentIds.contains(folderId), loadErrorsByDocumentId[folderId] == nil {
            return
        }

        lastLoadedDocumentId = folderId
        loadingDocumentIds.insert(folderId)
        loadErrorsByDocumentId[folderId] = nil
        defer {
            loadingDocumentIds.remove(folderId)
        }

        // Folder-level entities first, then each child — union preserves that order.
        let scopeIds = [folderId] + childDocumentIds
        var lists: [[Components.Schemas.KnowledgeEntity]] = []
        var lastError: Error?
        for docId in scopeIds {
            do {
                lists.append(try await entityService.listInspectorEntitiesForDocument(documentId: docId))
            } catch {
                if error.isCancellationError {
                    return  // superseded by a newer selection — keep current state
                }
                lastError = error  // partial aggregation beats none; remember for the all-failed case
            }
        }

        if lists.isEmpty, let lastError {
            entitiesByDocumentId[folderId] = []
            loadErrorsByDocumentId[folderId] = "Couldn't load entities: \(lastError.localizedDescription)"
            loadedDocumentIds.remove(folderId)
        } else {
            entitiesByDocumentId[folderId] = EntityStore.union(lists)
            loadErrorsByDocumentId.removeValue(forKey: folderId)
            loadedDocumentIds.insert(folderId)
        }
    }

    /// Re-fetch the current document scope (post-mutation / reconnect resync).
    func reload() async {
        let documentIds = loadedDocumentIds.isEmpty
            ? (lastLoadedDocumentId.map { [$0] } ?? [])
            : Array(loadedDocumentIds)
        for documentId in documentIds {
            await loadEntities(forDocument: documentId, force: true)
        }
    }

    func entities(forDocument documentId: String) -> [Components.Schemas.KnowledgeEntity] {
        entitiesByDocumentId[documentId] ?? []
    }

    /// Union entity lists (folder's own + each child's) preserving first-seen
    /// order, deduped by stable identity so the same entity referenced by
    /// multiple children collapses to one row (#3450). Pure + testable.
    static func union(
        _ lists: [[Components.Schemas.KnowledgeEntity]]
    ) -> [Components.Schemas.KnowledgeEntity] {
        var merged: [String: Components.Schemas.KnowledgeEntity] = [:]
        var order: [String] = []
        for list in lists {
            for entity in list {
                let key = aggregationKey(for: entity)
                if merged[key] == nil { order.append(key) }
                merged[key] = entity
            }
        }
        return order.compactMap { merged[$0] }
    }

    /// Dedup key for aggregation: the global entity id, else a type:name fallback
    /// for not-yet-persisted entities (mirrors the row's stable identity).
    static func aggregationKey(for entity: Components.Schemas.KnowledgeEntity) -> String {
        entity.id ?? "\(entity.entityType?.rawValue ?? "other"):\(entity.canonicalName)"
    }

    func isLoading(forDocument documentId: String) -> Bool {
        loadingDocumentIds.contains(documentId)
    }

    func loadError(forDocument documentId: String) -> String? {
        loadErrorsByDocumentId[documentId]
    }
}
