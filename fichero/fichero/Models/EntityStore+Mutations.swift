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
        // #4489 ①. This loop is the one behaviour change in an otherwise
        // deletion-only commit, and deleting the legacy mirror is what forced
        // it: the old code patched `libraryEntities` and the unread `entities`,
        // so the INSPECTOR — which reads these buckets — never saw the new
        // curation state from this call at all. Its caller does no reload
        // (`DocumentInspectorEntitiesTab+Actions.swift:112-127`), so the patch
        // was either redundant (the change stream repaired it) or wrong (it did
        // not), and never right.
        //
        // `rename` and `delete` already loop these buckets. Three mutations
        // agreed and this one forgot.
        for documentId in entitiesByDocumentId.keys {
            for index in entitiesByDocumentId[documentId]?.indices ?? (0..<0) {
                guard let id = entitiesByDocumentId[documentId]?[index].id,
                      targetIds.contains(id) else { continue }
                entitiesByDocumentId[documentId]?[index].curationState = state
            }
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
    /// Merge `absorbedIds` into `survivorId`, remove the absorbed rows in
    /// place, and patch the survivor row from a fresh fetch (#4389).
    ///
    /// `EntityAuditResponse` (the merge endpoint's return value) is an audit
    /// LOG record — id/operation_type/source_entity_ids/alias_changes — not
    /// the survivor's post-merge `KnowledgeEntity` state, so it can't patch
    /// the row by itself. Rather than extend that response (a backend
    /// schema + OpenAPI-regen change) or fall back to reloading the WHOLE
    /// list to recover one row, fetch the ONE row that actually changed:
    /// `getEntity(survivorId)` already exists for exactly this. Same
    /// N-vs-1 trade the issue asks for, without a two-stack change.
    func merge(absorbedIds: [String], into survivorId: String) async throws {
        _ = try await entityService.mergeEntities(
            absorbingEntityId: survivorId,
            absorbedEntityIds: absorbedIds
        )
        // #4489 ③: this used to prune `libraryEntities` and the per-document
        // buckets by hand and leave `libraryClaimCounts` alone, so absorbed ids
        // kept their claim-count entries forever.
        removeEntitiesEverywhere(ids: Set(absorbedIds))

        // The survivor gains aliases and its mention/claim counts change —
        // patch it from the server's canonical post-merge state, the same
        // way `rename` patches its row, rather than trusting a locally
        // guessed diff.
        let survivor = try await entityService.getEntity(survivorId)
        if let index = libraryEntities.firstIndex(where: { $0.id == survivorId }) {
            libraryEntities[index] = survivor
        }
        for documentId in entitiesByDocumentId.keys {
            if let index = entitiesByDocumentId[documentId]?.firstIndex(where: { $0.id == survivorId }) {
                entitiesByDocumentId[documentId]?[index] = survivor
            }
        }

        // The survivor's own claim count is wrong for exactly the reason the
        // merge happened, and it is the one number this method cannot derive:
        // absorbed counts do not simply sum, because two absorbed entities can
        // carry the same claim. `KnowledgeEntity` has no count field, so the
        // survivor's row above does not carry it either — the map is the only
        // source. Re-fetch it, matching this method's stated preference for the
        // server's canonical state over a guessed diff.
        //
        // Only when counts are actually held: an inspector-only session never
        // loaded them, and must not acquire a library-wide fetch from a merge.
        // A failure keeps the previous map rather than throwing, because the
        // merge itself succeeded — reporting it as failed would be a lie, and
        // blanking the map would render every survivor as zero claims.
        if !libraryClaimCounts.isEmpty {
            libraryClaimCounts = (try? await entityService.fetchClaimCounts()) ?? libraryClaimCounts
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
        }
        return updated
    }

    /// Delete the given entities, then remove the matching rows in place.
    func delete(entityIds: [String]) async throws {
        for entityId in entityIds {
            try await entityService.deleteEntity(entityId)
        }
        removeEntitiesEverywhere(ids: Set(entityIds))
    }

    /// The single place an entity is removed from every container this store
    /// holds (#4489 ② and ③).
    ///
    /// Three call sites need this — the local `delete`, the change-stream
    /// `deleted` branch, and `merge`'s absorbed ids — and each was separately
    /// responsible for remembering all three containers. Only `delete`
    /// remembered: `merge` forgot `libraryClaimCounts`, and the change-stream
    /// branch touched nothing at all, so a push delete and a local delete
    /// disagreed about what "deleted" means.
    ///
    /// **The containers themselves cannot be collapsed into one.**
    /// `libraryClaimCounts` is fetched from its own endpoint
    /// (`entityService.fetchClaimCounts`) and no claim count exists on
    /// `KnowledgeEntity`, so it is not derivable from `libraryEntities` the way
    /// the deleted legacy `entities` mirror was derivable from
    /// `entitiesByDocumentId`. What CAN be collapsed is the number of writers,
    /// and that is what this is: a fourth caller cannot forget a container,
    /// because there is no longer anywhere to forget it.
    func removeEntitiesEverywhere(ids: Set<String>) {
        guard !ids.isEmpty else { return }
        libraryEntities.removeAll { entity in
            entity.id.map(ids.contains) ?? false
        }
        libraryClaimCounts = libraryClaimCounts.filter { !ids.contains($0.key) }
        // Per-bucket `removeAll` rather than rebuilding the dictionary: the
        // store updates rows in place, it does not re-render whole lists.
        for documentId in entitiesByDocumentId.keys {
            entitiesByDocumentId[documentId]?.removeAll { entity in
                entity.id.map(ids.contains) ?? false
            }
        }
    }
}
