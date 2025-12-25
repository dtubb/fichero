import SwiftUI

/// Represents the complete state of the sidebar
struct SidebarState: Equatable {
    // Expansion state
    var expandedItems: Set<String> = []
    var libraryExpanded: Bool = true
    var searchesExpanded: Bool = true
    var chatExpanded: Bool = true
    var workflowsExpanded: Bool = true
    
    // UI state
    var isChatDropTargeted: Bool = false
    var renamingItemId: String? = nil
    var showingNewFolderDialog: Bool = false
    var newFolderParentId: String? = nil
    var newFolderSection: SidebarSection? = nil
    var newFolderName: String = ""
    var newFolderErrorMessage: String? = nil
    var isCreatingFolder: Bool = false
    var creatingFolderInlineId: String? = nil
    
    // Performance
    var scrollViewProxy: ScrollViewProxy? = nil
    
    /// Reset all state to default values
    mutating func reset() {
        expandedItems = []
        libraryExpanded = true
        searchesExpanded = true
        chatExpanded = true
        workflowsExpanded = true
        isChatDropTargeted = false
        renamingItemId = nil
        showingNewFolderDialog = false
        newFolderParentId = nil
        newFolderSection = nil
        newFolderName = ""
        newFolderErrorMessage = nil
        isCreatingFolder = false
        creatingFolderInlineId = nil
        scrollViewProxy = nil
    }
    
    /// Reset only folder creation related state
    mutating func resetFolderCreationState() {
        showingNewFolderDialog = false
        newFolderParentId = nil
        newFolderSection = nil
        newFolderName = ""
        newFolderErrorMessage = nil
        isCreatingFolder = false
        creatingFolderInlineId = nil
    }
}