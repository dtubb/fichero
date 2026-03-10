import SwiftUI

/// Manages rename state for sidebar items.
/// Use @StateObject in parent view, pass as @ObservedObject to children.
@MainActor
class RenameStateManager: ObservableObject {
    @Published var renamingItemId: String?
    @Published var editingName: String = ""

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
/// Use @StateObject in parent view, pass as @ObservedObject to children.
@MainActor
class DeleteStateManager: ObservableObject {
    @Published var showingDeleteConfirmation = false
    @Published var showingDeleteError = false
    @Published var itemToDelete: SidebarItem?
    @Published var deleteErrorMessage = ""

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
