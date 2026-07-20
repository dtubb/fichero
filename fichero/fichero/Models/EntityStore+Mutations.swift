import FicheroAPIClient
import Foundation

extension EntityStore {
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
}
