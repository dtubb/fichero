#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Entities Tab: Rename & Menus
//
// Members here are `internal` (not `private`) where a helper in another
// `DocumentInspectorEntitiesTab+*.swift` extension references them — a same-type
// extension in a different file cannot see a `private` member. The menu builders
// and targeting helpers used only within this file stay `private`.

extension DocumentInspectorEntitiesTab {
    // `internal`: also called from `entityNameView` in `+Rows.swift`.
    func beginRename(_ entity: Components.Schemas.KnowledgeEntity) {
        guard entity.id != nil else { return }
        renameDraft = entity.canonicalName
        renamingEntityId = entity.stableInspectorId
    }

    // `internal`: also called from `entityNameView` in `+Rows.swift`.
    func cancelRename() {
        renamingEntityId = nil
        renameFieldFocused = false
    }

    // `internal`: also called from `entityNameView` in `+Rows.swift`.
    /// Commit the inline rename through the entity store; the store PATCHes and
    /// republishes the list. The backend emits `entity.updated`, so the
    /// change-stream fans the refresh to other surfaces (EntityDetailView header)
    /// — the `.ficheroEntityUpdated` NotificationCenter nudge is now retired (#1862/#1865).
    func commitRename(for entity: Components.Schemas.KnowledgeEntity) {
        let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingEntityId = nil
        renameFieldFocused = false
        guard let entityId = entity.id,
              !trimmed.isEmpty,
              trimmed != entity.canonicalName else { return }

        Task {
            do {
                try await entityStore.rename(entityId: entityId, to: trimmed)
            } catch {
                inspectorEntitiesLogger.error(
                    "Entity rename failed for \(entityId, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
                actionMessage = "Couldn't rename entity: \(error.localizedDescription)"
            }
        }
    }

    // `internal`: called from `filterMenu` in `+Rows.swift`.
    func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    // `internal`: called from `entityRow` in `+Rows.swift`.
    @ViewBuilder
    func entityContextMenu(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        let targetEntities = contextMenuTargetEntities(for: entity)
        let targetCount = targetEntities.count

        Button("Rename") { beginRename(entity) }
            .disabled(entity.id == nil)
        Button("Find in Library") {
            postSearch(for: entity, kind: EntityKind(apiType: entity.entityType) ?? .other)
        }
        // Smart folder in ONE click (#4114): runs the mention search AND
        // persists it to the sidebar's saved searches.
        Button("Save Mentions as Smart Search") {
            postSearch(
                for: entity,
                kind: EntityKind(apiType: entity.entityType) ?? .other,
                saveAsSmartSearch: true
            )
        }
        // Row text can't use .textSelection (it fights row selection), so Copy
        // is the always-available copy-paste path for a selectable row (#3461).
        Button("Copy Name") {
            #if canImport(AppKit)
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(entity.canonicalName, forType: .string)
            #endif
        }
        if let entityId = entity.id {
            Button("Show in Graph") {
                kgFocusState.requestGraphReveal(entityId: entityId)
            }
        }
        Divider()

        Menu("Approve") {
            bulkScopeButtons(
                action: .approve,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        Menu("Reject") {
            bulkScopeButtons(
                action: .reject,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        Menu("Suppress") {
            bulkScopeButtons(
                action: .suppress,
                targetEntities: targetEntities
            )
        }
        .disabled(isApplyingBulkAction || targetCount == 0)

        mergeActionMenu(targetEntities: targetEntities, menuTitle: "Merge")
        deleteContextMenuButton(targetEntities: targetEntities)
    }

    // `private`: only `entityContextMenu` and `bulkActionMenu` (same file) use this.
    @ViewBuilder
    private func bulkScopeButtons(
        action: InspectorEntityBulkAction,
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button(bulkActionScopeLabel) {
            Task {
                await applyBulkAction(
                    action,
                    scope: .pageOrFolderOnly,
                    targetEntities: targetEntities
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyBulkAction(
                    action,
                    scope: .libraryWide,
                    targetEntities: targetEntities
                )
            }
        }
    }

    // `internal`: called from `entitiesMiniToolbar` in `+Rows.swift`.
    func bulkActionMenu(
        title: String,
        systemImage: String,
        action: InspectorEntityBulkAction
    ) -> some View {
        Menu {
            bulkScopeButtons(action: action, targetEntities: selectedEntities)
        } label: {
            Label(title, systemImage: systemImage)
        }
        .menuStyle(.borderlessButton)
        .disabled(isApplyingBulkAction || selectedEntities.isEmpty)
    }

    // `internal`: called from `entitiesMiniToolbar` in `+Rows.swift`.
    func mergeActionMenu(
        targetEntities: [Components.Schemas.KnowledgeEntity],
        menuTitle: String
    ) -> some View {
        // One destination choice per candidate so the user picks which entity
        // the others fold INTO (#2499). The heuristic survivor is marked
        // Recommended; picking any sets the confirmation plan.
        let recommendedId = InspectorEntityBulkSelection.mergeSurvivor(in: targetEntities)?.id
        let canMerge = InspectorEntityBulkSelection.mergePlan(for: targetEntities) != nil
        return Menu {
            if canMerge {
                ForEach(targetEntities, id: \.stableInspectorId) { entity in
                    if let id = entity.id,
                       let plan = InspectorEntityBulkSelection.mergePlan(
                            for: targetEntities, survivorId: id) {
                        Button(mergeDestinationLabel(
                            name: entity.canonicalName,
                            isRecommended: id == recommendedId
                        )) {
                            pendingMergePlan = plan
                        }
                    }
                }
            } else {
                Button("Requires 2+ same-kind saved entities") {}
                    .disabled(true)
            }
        } label: {
            Label(menuTitle, systemImage: "arrow.triangle.merge")
        }
        .menuStyle(.borderlessButton)
        .disabled(isApplyingBulkAction || !canMerge)
    }

    // `private`: only `mergeActionMenu` (same file) uses this.
    /// Menu-button title for a merge destination (#2499). Marks the heuristic
    /// survivor as "(Recommended)" so the sensible default is one click away.
    private func mergeDestinationLabel(name: String, isRecommended: Bool) -> String {
        isRecommended ? "Into \"\(name)\" (Recommended)" : "Into \"\(name)\""
    }

    // `internal`: called from `entitiesMiniToolbar` in `+Rows.swift`.
    func deleteActionButton(
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button(role: .destructive) {
            requestDeleteAction(for: targetEntities)
        } label: {
            Label("Delete", systemImage: "trash")
        }
        .buttonStyle(.borderless)
        .disabled(isApplyingBulkAction || targetEntities.isEmpty)
    }

    // `private`: only `entityContextMenu` (same file) uses this.
    @ViewBuilder
    private func deleteContextMenuButton(
        targetEntities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Button("Delete…", role: .destructive) {
            requestDeleteAction(for: targetEntities)
        }
        .disabled(isApplyingBulkAction || targetEntities.isEmpty)
    }

    // `internal`: called from `entityRow` in `+Rows.swift`.
    /// Single-click selects (native List); double-click opens the entity. (Finder-style.)
    func openEntity(_ entity: Components.Schemas.KnowledgeEntity) {
        if let id = entity.id {
            onEntitySelect?(id)
        } else {
            postSearch(for: entity, kind: EntityKind(apiType: entity.entityType) ?? .other)
        }
    }

    // `private`: only `entityContextMenu` (same file) uses this.
    private func contextMenuTargetEntities(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> [Components.Schemas.KnowledgeEntity] {
        if entitySelection.contains(entity.stableInspectorId) {
            return selectedEntities
        }
        return [entity]
    }

    // `private`: only `deleteActionButton` and `deleteContextMenuButton` (same file) use this.
    private func requestDeleteAction(for targetEntities: [Components.Schemas.KnowledgeEntity]) {
        pendingDeleteConfirmation = PendingEntityDeleteConfirmation(entities: targetEntities)
    }
}
