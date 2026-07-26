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

    // Optional callbacks for automation actions
    var onPause: (() -> Void)?
    var onResume: (() -> Void)?
    var onTrigger: (() -> Void)?  // For schedules - "Run Now"
    var onCancel: (() -> Void)?   // For batches - "Cancel"
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

            Button(action: { renameItem(item) }, label: {
                Label("Rename", systemImage: "pencil")
            })
            .disabled(!item.itemType.canBeRenamed)

            if let onDuplicate, itemTypeSupportsDuplicate {
                Button(action: onDuplicate, label: {
                    Label("Duplicate", systemImage: "plus.square.on.square")
                })
            }

            if let onMakeAlias, case .document = item.itemType {
                Button(action: onMakeAlias, label: {
                    Label("Make Alias", systemImage: "arrowshape.turn.up.right")
                })
            }

            Divider()

            Button(action: { deleteItems(resolvedDeleteTargets) }, label: {
                Label(deleteButtonTitle, systemImage: "trash")
                    .foregroundColor(.red)
            })
            .keyboardShortcut(.delete, modifiers: .command)
            .disabled(!resolvedDeleteTargets.contains { $0.itemType.canBeDeleted })
        }
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

    private var deleteButtonTitle: String {
        let count = resolvedDeleteTargets.count
        return count > 1 ? "Delete \(count) Items" : "Delete"
    }

    @ViewBuilder
    private var automationActions: some View {
        switch item.itemType {
        case .schedule(let schedule):
            if schedule.status == "active" {
                Button {
                    onPause?()
                } label: {
                    Label("Pause", systemImage: "pause")
                }

                Button {
                    onTrigger?()
                } label: {
                    Label("Run Now", systemImage: "play.fill")
                }
            } else if schedule.status == "paused" {
                Button {
                    onResume?()
                } label: {
                    Label("Resume", systemImage: "play")
                }
            }

        case .trigger(let trigger):
            if trigger.status == "active" {
                Button {
                    onPause?()
                } label: {
                    Label("Pause", systemImage: "pause")
                }
            } else if trigger.status == "paused" {
                Button {
                    onResume?()
                } label: {
                    Label("Resume", systemImage: "play")
                }
            }

        case .batch(let batch):
            if batch.status == "running" || batch.status == "pending" {
                Button {
                    onPause?()
                } label: {
                    Label("Pause", systemImage: "pause")
                }

                Button {
                    onCancel?()
                } label: {
                    Label("Cancel", systemImage: "xmark.circle")
                }
            }

        default:
            EmptyView()
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
        case .document, .savedSearch, .conversation, .workflow, .folder, .chain, .schedule, .trigger, .libraryHeader:
            return true
        case .comparison, .batch, .activityRun:
            return false
        }
    }

    var canBeDeleted: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow, .folder:
            return true
        case .chain, .schedule, .trigger, .batch:
            return true
        case .comparison, .activityRun, .libraryHeader:
            return false
        }
    }
}
