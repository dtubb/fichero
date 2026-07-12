// swiftlint:disable file_length
import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// One graph-context merge-candidate pair (#3318) from
/// `/api/kg/entity-curation/candidates` — two entities whose claim-neighborhoods
/// overlap (Jaccard), surfaced for user-confirmed merge. Never merged
/// automatically.
struct EntityReconciliationCandidate: Identifiable, Hashable {
    let entityAId: String
    let entityAName: String
    let entityBId: String
    let entityBName: String
    let jaccard: Double
    let entityType: String?

    var id: String { "\(entityAId)|\(entityBId)" }
}

/// Observable domain store for knowledge entities (#1885, keystone template).
///
/// The single endpoint accessor for the entity list a view renders. A view
/// never calls `EntityServiceGenerated` / `KGCurationServiceGenerated`
/// directly: it observes `entities` and dispatches the named actions below.
/// Each action performs the typed write and then refreshes the current scope —
/// today via an explicit reload (no backend push yet), and via `apply(_:)`
/// once the per-library change-stream (#1863) starts emitting. Swapping reload
/// for push is then a no-op at every call site.
///
/// Mirrors `WorkflowExecutionObserver`: typed event in → mutate observable
/// state → SwiftUI re-renders every bound view. One instance per library
/// (registered on `LibraryReference`), shared across that library's windows.
@MainActor
@Observable
// swiftlint:disable:next type_body_length
final class EntityStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var entities: [Components.Schemas.KnowledgeEntity] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var libraryEntities: [Components.Schemas.KnowledgeEntity] = []
    private(set) var libraryClaimCounts: [String: Int] = [:]
    private(set) var isLoadingLibrary = false
    private(set) var libraryLoadError: String?
    private(set) var entitiesByDocumentId: [String: [Components.Schemas.KnowledgeEntity]] = [:]
    private(set) var loadingDocumentIds: Set<String> = []
    private(set) var loadErrorsByDocumentId: [String: String] = [:]

    // ─── Transport: the EXISTING generated wrappers, unchanged ───
    private let entityService: EntityServiceGenerated
    private let kgCurationService: KGCurationServiceGenerated
    private let libraryPath: String
    private let log = Logger(subsystem: "app.fichero.fichero", category: "EntityStore")

    /// Document scopes that have been loaded successfully. Multiple inspector
    /// windows on the same library can keep different document buckets warm
    /// without thrashing each other's visible list (#1908).
    private var loadedDocumentIds: Set<String> = []
    private var lastLoadedDocumentId: String?
    private var lastLibraryQuery: String?

    init(
        entityService: EntityServiceGenerated,
        kgCurationService: KGCurationServiceGenerated,
        libraryPath: String
    ) {
        self.entityService = entityService
        self.kgCurationService = kgCurationService
        self.libraryPath = libraryPath
    }

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
        } catch is CancellationError {
            // Superseded by a newer search/load.
        } catch {
            libraryEntities = []
            libraryLoadError = "Couldn't load entities: \(error.localizedDescription)"
        }
    }

    /// Load the inspector entities for `documentId`. Idempotent: re-loading the
    /// same already-populated scope is a no-op unless `force` is set (reload
    /// button / post-mutation refresh).
    func loadEntities(forDocument documentId: String, force: Bool = false) async {
        if !force, loadedDocumentIds.contains(documentId), loadErrorsByDocumentId[documentId] == nil {
            syncLegacyScope(documentId: documentId)
            return
        }

        lastLoadedDocumentId = documentId
        loadingDocumentIds.insert(documentId)
        loadErrorsByDocumentId[documentId] = nil
        syncLegacyScope(documentId: documentId)
        defer {
            loadingDocumentIds.remove(documentId)
            syncLegacyScope(documentId: documentId)
        }
        do {
            let loaded = try await entityService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
            entitiesByDocumentId[documentId] = loaded
            loadErrorsByDocumentId.removeValue(forKey: documentId)
            loadedDocumentIds.insert(documentId)
            syncLegacyScope(documentId: documentId)
            log.debug(
                "Loaded \(loaded.count, privacy: .public) entities for \(documentId, privacy: .public)"
            )
        } catch is CancellationError {
            // Superseded by a newer document selection — keep current state.
        } catch {
            entitiesByDocumentId[documentId] = []
            loadErrorsByDocumentId[documentId] = "Couldn't load entities: \(error.localizedDescription)"
            loadedDocumentIds.remove(documentId)
            syncLegacyScope(documentId: documentId)
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
            syncLegacyScope(documentId: folderId)
            return
        }

        lastLoadedDocumentId = folderId
        loadingDocumentIds.insert(folderId)
        loadErrorsByDocumentId[folderId] = nil
        syncLegacyScope(documentId: folderId)
        defer {
            loadingDocumentIds.remove(folderId)
            syncLegacyScope(documentId: folderId)
        }

        // Folder-level entities first, then each child — union preserves that order.
        let scopeIds = [folderId] + childDocumentIds
        var lists: [[Components.Schemas.KnowledgeEntity]] = []
        var lastError: Error?
        for docId in scopeIds {
            do {
                lists.append(try await entityService.listInspectorEntitiesForDocument(documentId: docId))
            } catch is CancellationError {
                return  // superseded by a newer selection — keep current state
            } catch {
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
        syncLegacyScope(documentId: folderId)
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

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// Set the curation state of `entityIds` and optionally write library-wide
    /// suppress rules, then patch the loaded rows in place. Throws so the
    /// calling view can surface a precise message and keep its own UI feedback
    /// state.
    func setCuration(
        entityIds: [String],
        to state: Components.Schemas.EntityCurationState,
        suppressRules: [Components.Schemas.EntityRuleCreateRequest] = []
    ) async throws {
        if !entityIds.isEmpty {
            _ = try await kgCurationService.batchSetEntityCurationState(
                entityIds: entityIds,
                curationState: state
            )
        }
        if !suppressRules.isEmpty {
            _ = try await kgCurationService.batchCreateEntityRules(suppressRules)
        }
        guard !entityIds.isEmpty else { return }
        let targetIds = Set(entityIds)
        for index in libraryEntities.indices {
            guard let id = libraryEntities[index].id, targetIds.contains(id) else { continue }
            libraryEntities[index].curationState = state
        }
        for index in entities.indices {
            guard let id = entities[index].id, targetIds.contains(id) else { continue }
            entities[index].curationState = state
        }
    }

    /// Graph-context duplicate candidate pairs for a reconciliation scope
    /// (#3318), from `/api/kg/entity-curation/candidates`. The store is the only
    /// endpoint accessor; the reconciliation sheet reads these.
    func reconciliationCandidates(
        scope: String,
        folderId: String?
    ) async throws -> [EntityReconciliationCandidate] {
        let data = try await entityService.reconciliationCandidates(scope: scope, folderId: folderId)
        return Self.parseReconciliationCandidates(data)
    }

    /// Parse the candidate-pairs envelope (`{ items: [...], count }`) into typed
    /// pairs. The OpenAPI `items` schema is freeform, so parse defensively.
    /// Exposed for tests.
    static func parseReconciliationCandidates(_ data: Data) -> [EntityReconciliationCandidate] {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = obj["items"] as? [[String: Any]] else { return [] }
        return items.compactMap { item -> EntityReconciliationCandidate? in
            guard let aId = item["entity_a_id"] as? String,
                  let bId = item["entity_b_id"] as? String,
                  aId != bId else { return nil }
            return EntityReconciliationCandidate(
                entityAId: aId,
                entityAName: item["entity_a_name"] as? String ?? aId,
                entityBId: bId,
                entityBName: item["entity_b_name"] as? String ?? bId,
                jaccard: (item["jaccard"] as? Double) ?? 0,
                entityType: item["entity_type"] as? String
            )
        }
    }

    /// Merge `absorbedIds` into `survivorId`, then re-fetch the active
    /// document-scoped inspector list so every surface sees the canonical
    /// post-merge rows from the backend.
    func merge(absorbedIds: [String], into survivorId: String) async throws {
        _ = try await entityService.mergeEntities(
            absorbingEntityId: survivorId,
            absorbedEntityIds: absorbedIds
        )
        let absorbed = Set(absorbedIds)
        libraryEntities.removeAll { entity in
            entity.id.map(absorbed.contains) ?? false
        }
        if hasDocumentScope {
            await reload()
            return
        }

        entities.removeAll { entity in
            entity.id.map(absorbed.contains) ?? false
        }
        for documentId in entitiesByDocumentId.keys {
            entitiesByDocumentId[documentId]?.removeAll { entity in
                entity.id.map(absorbed.contains) ?? false
            }
        }
    }

    /// Rename an entity's canonical name, then patch the matching row in place.
    /// Returns the updated entity so the caller can notify not-yet-migrated
    /// surfaces (#1865).
    @discardableResult
    func rename(
        entityId: String,
        to newName: String
    ) async throws -> Components.Schemas.KnowledgeEntity {
        let updated = try await entityService.patchEntity(entityId, canonicalName: newName)
        if let index = libraryEntities.firstIndex(where: { $0.id == entityId }) {
            libraryEntities[index] = updated
        }
        if let index = entities.firstIndex(where: { $0.id == entityId }) {
            entities[index] = updated
        }
        for documentId in entitiesByDocumentId.keys {
            if let index = entitiesByDocumentId[documentId]?.firstIndex(where: { $0.id == entityId }) {
                entitiesByDocumentId[documentId]?[index] = updated
            }
        }
        return updated
    }

    /// Change an entity's type, then re-fetch the active inspector scope so
    /// grouped sections and row placement stay canonical.
    @discardableResult
    func reclassify(
        entityId: String,
        to entityType: String
    ) async throws -> Components.Schemas.KnowledgeEntity {
        let updated = try await entityService.patchEntity(entityId, entityType: entityType)
        if let index = libraryEntities.firstIndex(where: { $0.id == entityId }) {
            libraryEntities[index] = updated
        }
        if hasDocumentScope {
            await reload()
        } else if let index = entities.firstIndex(where: { $0.id == entityId }) {
            entities[index] = updated
        }
        return updated
    }

    /// Delete the given entities, then remove the matching rows in place.
    func delete(entityIds: [String]) async throws {
        for entityId in entityIds {
            try await entityService.deleteEntity(entityId)
        }
        let deleted = Set(entityIds)
        libraryEntities.removeAll { entity in
            entity.id.map(deleted.contains) ?? false
        }
        libraryClaimCounts = libraryClaimCounts.filter { !deleted.contains($0.key) }
        entities.removeAll { entity in
            entity.id.map(deleted.contains) ?? false
        }
        for documentId in entitiesByDocumentId.keys {
            entitiesByDocumentId[documentId]?.removeAll { entity in
                entity.id.map(deleted.contains) ?? false
            }
        }
    }

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

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for non-delete verbs) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()

    private func syncLegacyScope(documentId: String) {
        entities = entitiesByDocumentId[documentId] ?? []
        isLoading = loadingDocumentIds.contains(documentId)
        loadError = loadErrorsByDocumentId[documentId]
    }

    private var hasDocumentScope: Bool {
        !loadedDocumentIds.isEmpty || lastLoadedDocumentId != nil
    }
}
