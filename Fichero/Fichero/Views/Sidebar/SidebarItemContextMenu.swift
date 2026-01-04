import SwiftUI
import OSLog

/// Structured logger for context menu operations.
private let logger = Logger(subsystem: "com.fichero.app", category: "SidebarContextMenu")

/// Context menu for sidebar items (rename, delete).
///
/// Provides standard actions for sidebar items with keyboard shortcuts.
/// Actions are disabled based on item capabilities (see `SidebarItem.ItemType` extensions).
struct SidebarItemContextMenu: View {
    let item: SidebarItem
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager

    var body: some View {
        Group {
            Button(action: { renameItem(item) }, label: {
                Label("Rename", systemImage: "pencil")
            })
            .disabled(!item.itemType.canBeRenamed)

            Divider()

            Button(action: { deleteItem(item) }, label: {
                Label("Delete", systemImage: "trash")
                    .foregroundColor(.red)
            })
            .keyboardShortcut(.delete, modifiers: .command)
            .disabled(!item.itemType.canBeDeleted)
        }
    }

    private func renameItem(_ item: SidebarItem) {
        logger.debug(" renameItem called for: \(item.name) (id: \(item.id))")
        renameState.startRename(itemId: item.id, currentName: item.name)
        logger.debug("   - Set renameState.renamingItemId to: \(item.id)")
    }

    private func deleteItem(_ item: SidebarItem) {
        logger.debug(" deleteItem called for: \(item.name) (id: \(item.id))")
        deleteState.showDeleteConfirmation(for: item)
        logger.debug("   - Set deleteState.itemToDelete to: \(item.name)")
    }
}

// MARK: - Extensions to add capability checks to ItemType

extension SidebarItem.ItemType {
    var canBeRenamed: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow, .folder:
            return true
        case .libraryHeader:
            return false
        }
    }

    var canBeDeleted: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow, .folder:
            return true
        case .libraryHeader:
            return false
        }
    }
}
