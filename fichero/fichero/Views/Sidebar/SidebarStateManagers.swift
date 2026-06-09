import SwiftUI

/// Manages rename state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class RenameStateManager {
    var renamingItemId: String?
    var editingName: String = ""

    func startRename(itemId: String, currentName: String) {
        renamingItemId = itemId
        editingName = currentName
    }

    func cancelRename() {
        renamingItemId = nil
        editingName = ""
    }
}

/// Manages delete confirmation state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class DeleteStateManager {
    var showingDeleteConfirmation = false
    var showingDeleteError = false
    var itemToDelete: SidebarItem?
    var deleteErrorMessage = ""

    func showDeleteConfirmation(for item: SidebarItem) {
        itemToDelete = item
        showingDeleteConfirmation = true
    }

    func cancelDelete() {
        showingDeleteConfirmation = false
        showingDeleteError = false
        itemToDelete = nil
        deleteErrorMessage = ""
    }

    func showError(message: String) {
        deleteErrorMessage = message
        showingDeleteError = true
        showingDeleteConfirmation = false
    }
}
