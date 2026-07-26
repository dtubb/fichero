import Observation
import SwiftUI

/// Manages sidebar state with persistence across app relaunches
/// Stores expansion states per window
@MainActor
@Observable
class SidebarState {
    // MARK: - Persisted State (saved to UserDefaults)

    /// Individual item expansion states (folder/library headers)
    var expandedItems: Set<String> {
        didSet { saveExpandedItems() }
    }

    /// Library expansion states (library ID -> expanded)
    var libraryExpansionStates: [String: Bool] {
        didSet { saveLibraryExpansionStates() }
    }

    // MARK: - Transient State (not persisted)

    var isChatDropTargeted: Bool = false
    var isLibraryDropTargeted: Bool = false
    var renamingItemId: String?
    var showingFileImporter: Bool = false
    var selectedImportMode: IngestMode = .link
    var showingNewFolderDialog: Bool = false
    var newFolderParentId: String?
    var newFolderCategory: ItemCategory?
    var newFolderName: String = ""
    var newFolderErrorMessage: String?
    var isCreatingFolder: Bool = false
    var creatingFolderInlineId: String?

    // Automation creation state
    var showingScheduleCreation: Bool = false
    var showingTriggerCreation: Bool = false
    var selectedWorkflowForAutomation: WorkflowSidebarItem?

    // Drag and drop state
    var isProcessingDrop: Bool = false
    var dropProgress: Double = 0.0
    var dropErrorMessage: String?
    /// Rename failures were log-only; surface them like drop failures do.
    var renameErrorMessage: String?
    var dropSuccessCount: Int = 0
    var dropFailureCount: Int = 0

    // Performance
    var scrollViewProxy: ScrollViewProxy?

    // MARK: - Persistence

    private let windowId: String
    private var expandedItemsKey: String { "sidebar.expanded.\(windowId)" }
    private var libraryExpansionKey: String { "sidebar.libraries.\(windowId)" }

    init(windowId: String = "main") {
        self.windowId = windowId

        // Load persisted expanded items
        let itemsKey = "sidebar.expanded.\(windowId)"
        if let saved = UserDefaults.standard.array(forKey: itemsKey) as? [String] {
            self.expandedItems = Set(saved)
        } else {
            self.expandedItems = []
        }

        // Load persisted library expansion states (default: all expanded)
        let libKey = "sidebar.libraries.\(windowId)"
        if let saved = UserDefaults.standard.dictionary(forKey: libKey) as? [String: Bool] {
            self.libraryExpansionStates = saved
        } else {
            self.libraryExpansionStates = [:]
        }

        // Purge stale persistence from the retired unified-section headers
        // (removed when the per-library sub-sections collapsed into one node list).
        UserDefaults.standard.removeObject(forKey: "sidebar.unified.sections.\(windowId)")
    }

    // MARK: - State Management

    /// Toggle expansion for an item
    func toggleExpansion(for itemId: String) {
        if expandedItems.contains(itemId) {
            expandedItems.remove(itemId)
        } else {
            expandedItems.insert(itemId)
        }
    }

    /// Check if item is expanded
    func isExpanded(_ itemId: String) -> Bool {
        expandedItems.contains(itemId)
    }

    /// Toggle library expansion
    func toggleLibraryExpansion(for libraryId: UUID) {
        let key = libraryId.uuidString
        let currentState = libraryExpansionStates[key] ?? true  // Default: expanded
        libraryExpansionStates[key] = !currentState
    }

    /// Check if library is expanded (default: true)
    func isLibraryExpanded(_ libraryId: UUID) -> Bool {
        let key = libraryId.uuidString
        return libraryExpansionStates[key] ?? true
    }

    /// Reset all state to defaults
    func reset() {
        expandedItems = []
        libraryExpansionStates = [:]

        // Reset transient state
        isChatDropTargeted = false
        isLibraryDropTargeted = false
        renamingItemId = nil
        showingNewFolderDialog = false
        newFolderParentId = nil
        newFolderCategory = nil
        newFolderName = ""
        newFolderErrorMessage = nil
        isCreatingFolder = false
        creatingFolderInlineId = nil
        isProcessingDrop = false
        dropProgress = 0.0
        dropErrorMessage = nil
        renameErrorMessage = nil
        dropSuccessCount = 0
        dropFailureCount = 0
        scrollViewProxy = nil
    }

    /// Reset folder creation state
    func resetFolderCreationState() {
        showingNewFolderDialog = false
        newFolderParentId = nil
        newFolderCategory = nil
        newFolderName = ""
        newFolderErrorMessage = nil
        isCreatingFolder = false
        creatingFolderInlineId = nil
    }

    // MARK: - Private Persistence Methods

    private func saveExpandedItems() {
        UserDefaults.standard.set(Array(expandedItems), forKey: expandedItemsKey)
    }

    private func saveLibraryExpansionStates() {
        UserDefaults.standard.set(libraryExpansionStates, forKey: libraryExpansionKey)
    }
}
