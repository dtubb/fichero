import OSLog
import SwiftUI

/// Structured logger for context menu operations.
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarContextMenu")

/// Context menu for sidebar items (rename, delete, and type-specific actions).
///
/// Provides standard actions for sidebar items with keyboard shortcuts.
/// Actions are disabled based on item capabilities (see `SidebarItem.ItemType` extensions).
struct SidebarItemContextMenu: View {
    let item: SidebarItem
    /// What Delete acts on: `[item]` for a lone row, the whole deletable
    /// selection when the clicked row is part of a multi-selection
    /// (see `sidebarContextDeleteTargets`). Empty means "just the item".
    var deleteTargets: [SidebarItem] = []
    @Bindable var renameState: RenameStateManager
    @Bindable var deleteState: DeleteStateManager

    /// A schedule's, trigger's or batch's own verbs (#5712): the engine's actions, as Project › Workflows ▸ offers them.
    var automation: AutomationVerbsTarget?
    /// Workflow rows only: duplicate via the backend endpoint — also the
    /// blessed path for editing locked Default presets ("Default workflows
    /// are read-only; duplicate to edit", engine 403).
    var onDuplicate: (() -> Void)?
    /// Document rows: create a Finder-style alias (engine alias node via
    /// the bookmarks surface, #2591) beside the original.
    var onMakeAlias: (() -> Void)?

    var body: some View {
        Group {
            // Type-specific actions first
            automationActions

            if hasTypeSpecificActions {
                Divider()
            }

            // Rename and Delete: the shared items Edit renders (#5652).
            RenameItemMenuItem(target: renameTarget)

            // File's own Duplicate and Make Alias (#5652), on this row.
            if onDuplicate != nil, itemTypeSupportsDuplicate {
                DuplicateItemMenuItem(target: copyTarget)
            }

            if onMakeAlias != nil, case .document = item.itemType {
                MakeAliasMenuItem(target: copyTarget)
            }

            Divider()

            DeleteItemsMenuItem(target: deleteTarget)
                .keyboardShortcut(.delete, modifiers: .command)
        }
    }

    /// This row, as Duplicate and Make Alias act on it.
    private var copyTarget: ItemVerbsTarget {
        var target = ItemVerbsTarget(ids: [item.id], documents: [])
        if let onDuplicate { target.duplicate = { onDuplicate() } }
        if let onMakeAlias { target.makeAlias = { onMakeAlias() } }
        return target
    }

    /// This row, as Rename acts on it.
    private var renameTarget: ItemVerbsTarget {
        var target = ItemVerbsTarget(ids: [item.id], documents: [])
        if item.itemType.canBeRenamed { target.rename = { renameItem(item) } }
        return target
    }

    /// What Delete acts on here: the row, or the deletable selection it is part of.
    private var deleteTarget: ItemVerbsTarget {
        let targets = resolvedDeleteTargets
        var target = ItemVerbsTarget(ids: targets.map(\.id), documents: [])
        target.deletableCount = targets.filter { $0.itemType.canBeDeleted }.count
        if target.deletableCount > 0 { target.delete = { deleteItems(targets) } }
        return target
    }

    /// Kinds with a backend duplicate endpoint.
    private var itemTypeSupportsDuplicate: Bool {
        switch item.itemType {
        case .document, .workflow, .savedSearch, .conversation:
            return true
        default:
            return false
        }
    }

    private var resolvedDeleteTargets: [SidebarItem] {
        deleteTargets.isEmpty ? [item] : deleteTargets
    }

    /// An automation row's own verbs (#5712): what its state allows, each the engine's own action.
    @ViewBuilder
    private var automationActions: some View {
        if let automation {
            ForEach(automation.offered, id: \.self) { verb in
                AutomationVerbMenuItem(verb: verb, target: automation)
            }
        }
    }

    private var hasTypeSpecificActions: Bool {
        switch item.itemType {
        case .schedule, .trigger, .batch:
            return true
        default:
            return false
        }
    }

    private func renameItem(_ item: SidebarItem) {
        logger.debug(" renameItem called for: \(item.name) (id: \(item.id))")
        renameState.startRename(itemId: item.id, currentName: item.name)
        logger.debug("   - Set renameState.renamingItemId to: \(item.id)")
    }

    private func deleteItems(_ items: [SidebarItem]) {
        logger.debug(" deleteItems called for \(items.count) item(s), clicked: \(item.name)")
        deleteState.showDeleteConfirmation(for: items)
    }
}

// MARK: - Extensions to add capability checks to ItemType

extension SidebarItem.ItemType {
    var canBeRenamed: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow, .chain, .schedule, .trigger, .libraryHeader:
            return true
        // `.folder` removed (#116). It is the SAME virtual row `canBeDeleted`
        // excludes below for #4454 — "no data, just structure" — and Rename had
        // exactly the failure Delete had: the menu item was enabled, the user
        // typed a new name, and committing fell through to `default:` in
        // `SidebarItemRow+Rename.swift`, logged "Unknown item type for rename",
        // and returned. Confirmed action, no change, no error.
        //
        // Delete was fixed here and Rename was left, in this file, for the same
        // rows — the one-of-two-identical-cases miss that #4415 and #4416 were
        // also instances of.
        case .comparison, .batch, .activityRun, .folder:
            return false
        }
    }

    var canBeDeleted: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow:
            return true
        case .chain, .schedule, .trigger, .batch:
            return true
        // `.folder(folderPath:)` is a VIRTUAL row — "no data, just structure",
        // per its declaration. It is a grouping in the tree, not a library
        // folder: a real folder is a `Document` with `docType == .folder` and
        // deletes through `.document` above. There is nothing behind a
        // structural row to delete, so offering Delete could only ever no-op,
        // which is what it did — confirmed destructive action, log line, no
        // change (#4454).
        case .comparison, .activityRun, .libraryHeader, .folder:
            return false
        }
    }
}
