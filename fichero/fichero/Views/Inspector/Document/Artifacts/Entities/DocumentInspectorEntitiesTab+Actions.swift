import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Entities Tab: Selection Sync, Drops & Actions
//
// Members here are `internal` (not `private`) where the core file's `body` or
// another `DocumentInspectorEntitiesTab+*.swift` extension references them — a
// same-type extension in a different file cannot see a `private` member.
// `restoreSelectionAfterEntityRefresh` stays `private`: it is only used here.

extension DocumentInspectorEntitiesTab {
    // `internal`: called from `body` in the core file.
    func syncSelectionToLoadedEntities() {
        let validIds = Set(orderedEntities.map(\.stableInspectorId))
        entitySelection = entitySelection.intersection(validIds)
        syncSelectionToFocusedEntity()
    }

    // `internal`: called from `body` in the core file.
    func syncSelectionToFocusedEntity() {
        guard let selectedEntityId,
              let entity = orderedEntities.first(where: { $0.id == selectedEntityId }) else { return }
        let stableId = entity.stableInspectorId
        guard entitySelection != [stableId] else { return }
        entitySelection = [stableId]
    }

    // `internal`: called from `body` in the core file.
    func routeSelectionToInspector() {
        guard entitySelection.count == 1,
              let entity = selectedEntities.first,
              let id = entity.id else { return }
        onEntitySelect?(id)
    }

    // `internal`: called from `entityRow` in `+Rows.swift`.
    func dropTargetHandler(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> (Bool) -> Void {
        { isTargeted in
            if isTargeted {
                dropTargetEntityId = entity.stableInspectorId
            } else if dropTargetEntityId == entity.stableInspectorId {
                dropTargetEntityId = nil
            }
        }
    }

    // `internal`: called from `entityRow` in `+Rows.swift`.
    func handleEntityDrop(
        payloads: [InspectorEntityDragID],
        onto target: Components.Schemas.KnowledgeEntity
    ) -> Bool {
        dropTargetEntityId = nil
        guard let payload = payloads.first,
              payload.id != target.stableInspectorId,
              let dragged = orderedEntities.first(where: { $0.stableInspectorId == payload.id }) else {
            return false
        }

        let draggedKind = EntityKind(apiType: dragged.entityType) ?? .other
        let targetKind = EntityKind(apiType: target.entityType) ?? .other

        if draggedKind == targetKind,
           let targetId = target.id,
           let plan = InspectorEntityBulkSelection.mergePlan(
                for: [dragged, target],
                survivorId: targetId
           ) {
            pendingMergePlan = plan
            return true
        }

        guard let draggedId = dragged.id,
              let targetType = targetKind.apiTypeId,
              draggedKind.apiTypeId != targetType else {
            return false
        }

        pendingReclassifyPlan = PendingEntityReclassifyPlan(
            entityId: draggedId,
            entityName: dragged.canonicalName,
            entityType: targetType,
            targetLabel: targetKind.label
        )
        return true
    }

    // `internal`: called from `bulkScopeButtons` in `+Menus.swift`.
    func applyBulkAction(
        _ action: InspectorEntityBulkAction,
        scope: InspectorEntityBulkActionScope,
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) async {
        let entityIds = targetEntities.compactMap(\.id)
        let missingIdCount = targetEntities.count - entityIds.count
        guard !entityIds.isEmpty || (action == .suppress && scope == .libraryWide) else {
            actionMessage = "Selected entities are missing IDs, so \(action.verb.lowercased()) was skipped."
            return
        }

        isApplyingBulkAction = true
        actionMessage = nil
        defer { isApplyingBulkAction = false }

        do {
            let suppressRules = action == .suppress && scope == .libraryWide
                ? InspectorEntityBulkSelection.libraryWideSuppressRules(for: targetEntities)
                : []
            try await entityStore.setCuration(
                entityIds: entityIds,
                to: action.curationState,
                suppressRules: suppressRules
            )

            var message = "\(action.verb) \(entityIds.count) entit"
            message += entityIds.count == 1 ? "y" : "ies"
            if action == .suppress, scope == .libraryWide {
                message += " and wrote \(suppressRules.count) suppress rule"
                message += suppressRules.count == 1 ? "" : "s"
            }
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            actionMessage = message
        } catch {
            inspectorEntitiesLogger.error(
                "Bulk entity action failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't \(action.verb.lowercased()) entities: \(error.localizedDescription)"
        }
    }

    // `internal`: called from `body` in the core file.
    func applyMerge(_ plan: InspectorEntityBulkSelection.MergePlan) async {
        isApplyingBulkAction = true
        actionMessage = nil
        pendingMergePlan = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.merge(
                absorbedIds: plan.absorbedEntityIds,
                into: plan.survivorId
            )
            actionMessage = "Merged \(plan.entityCount) entities into \(plan.survivorName)."
            restoreSelectionAfterEntityRefresh(entityId: plan.survivorId)
        } catch {
            inspectorEntitiesLogger.error(
                "Entity merge failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't merge entities: \(error.localizedDescription)"
        }
    }

    // `private`: only `applyMerge` and `applyReclassify` (same file) use this.
    private func restoreSelectionAfterEntityRefresh(entityId: String) {
        guard let entity = orderedEntities.first(where: { $0.id == entityId }) else {
            entitySelection = []
            return
        }
        entitySelection = [entity.stableInspectorId]
        onEntitySelect?(entityId)
    }

    // `internal`: called from `body` in the core file.
    func applyReclassify(_ plan: PendingEntityReclassifyPlan) async {
        isApplyingBulkAction = true
        actionMessage = nil
        pendingReclassifyPlan = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.reclassify(entityId: plan.entityId, to: plan.entityType)
            actionMessage = "Changed \(plan.entityName) to \(plan.targetLabel.lowercased())."
            restoreSelectionAfterEntityRefresh(entityId: plan.entityId)
        } catch {
            inspectorEntitiesLogger.error(
                "Entity type change failed for \(plan.entityId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't change entity type: \(error.localizedDescription)"
        }
    }

    // `internal`: called from `body` in the core file.
    func applyDelete(_ pending: PendingEntityDeleteConfirmation) async {
        let entityIds = pending.entities.compactMap(\.id)
        let missingIdCount = pending.entities.count - entityIds.count
        guard !entityIds.isEmpty else {
            actionMessage = "Selected entities are missing IDs, so delete was skipped."
            pendingDeleteConfirmation = nil
            return
        }

        isApplyingBulkAction = true
        actionMessage = nil
        pendingDeleteConfirmation = nil
        defer { isApplyingBulkAction = false }

        do {
            try await entityStore.delete(entityIds: entityIds)
            entitySelection = []

            var message = "Deleted \(entityIds.count) entit"
            message += entityIds.count == 1 ? "y" : "ies"
            if missingIdCount > 0 {
                message += "; skipped \(missingIdCount) without IDs"
            }
            actionMessage = message
        } catch {
            inspectorEntitiesLogger.error(
                "Entity delete failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            actionMessage = "Couldn't delete entities: \(error.localizedDescription)"
        }
    }

    // `internal`: called from `entityContextMenu` and `openEntity` in `+Menus.swift`.
    func postSearch(
        for entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) {
        entitySearchState?.request(
            name: entity.canonicalName,
            entityType: kind.searchScope
        )
    }
}
