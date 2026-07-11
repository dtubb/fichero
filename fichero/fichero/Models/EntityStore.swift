import FicheroAPIClient
import Foundation
import Observation
import OSLog

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
final class EntityStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var entities: [Components.Schemas.KnowledgeEntity] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    // ─── Transport: the EXISTING generated wrappers, unchanged ───
    private let entityService: EntityServiceGenerated
    private let kgCurationService: KGCurationServiceGenerated
    private let libraryPath: String
    private let log = Logger(subsystem: "app.fichero.fichero", category: "EntityStore")

    /// Per-document scoping cache — the inspector loads "entities for THIS
    /// document". `loadEntities` is idempotent against it unless forced.
    private var loadedDocumentId: String?

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

    /// Load the inspector entities for `documentId`. Idempotent: re-loading the
    /// same already-populated scope is a no-op unless `force` is set (reload
    /// button / post-mutation refresh).
    func loadEntities(forDocument documentId: String, force: Bool = false) async {
        if !force, loadedDocumentId == documentId, !entities.isEmpty { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let loaded = try await entityService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
            entities = loaded
            loadedDocumentId = documentId
            log.debug(
                "Loaded \(loaded.count, privacy: .public) entities for \(documentId, privacy: .public)"
            )
        } catch is CancellationError {
            // Superseded by a newer document selection — keep current state.
        } catch {
            loadError = "Couldn't load entities: \(error.localizedDescription)"
            entities = []
            loadedDocumentId = documentId
            log.error(
                "Failed to load entities for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    /// Re-fetch the current document scope (post-mutation / reconnect resync).
    func reload() async {
        guard let documentId = loadedDocumentId else { return }
        await loadEntities(forDocument: documentId, force: true)
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
        for index in entities.indices {
            guard let id = entities[index].id, targetIds.contains(id) else { continue }
            entities[index].curationState = state
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
        if loadedDocumentId != nil {
            await reload()
            return
        }

        let absorbed = Set(absorbedIds)
        entities.removeAll { entity in
            entity.id.map(absorbed.contains) ?? false
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
        if let index = entities.firstIndex(where: { $0.id == entityId }) {
            entities[index] = updated
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
        if loadedDocumentId != nil {
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
        entities.removeAll { entity in
            entity.id.map(deleted.contains) ?? false
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
}
