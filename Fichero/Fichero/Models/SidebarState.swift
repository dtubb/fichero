import SwiftUI

/// Manages sidebar state with persistence across app relaunches
/// Stores expansion states per window
@MainActor
class SidebarState: ObservableObject {
    // MARK: - Persisted State (saved to UserDefaults)

    /// Individual item expansion states (folder/library headers)
    @Published var expandedItems: Set<String> {
        didSet { saveExpandedItems() }
    }

    /// Library expansion states (library ID -> expanded)
    @Published var libraryExpansionStates: [String: Bool] {
        didSet { saveLibraryExpansionStates() }
    }

    // MARK: - Transient State (not persisted)

    @Published var isChatDropTargeted: Bool = false
    @Published var isLibraryDropTargeted: Bool = false
    @Published var renamingItemId: String?
    @Published var showingFileImporter: Bool = false
    @Published var showingNewFolderDialog: Bool = false
    @Published var newFolderParentId: String?
    @Published var newFolderCategory: ItemCategory?
    @Published var newFolderName: String = ""
    @Published var newFolderErrorMessage: String?
    @Published var isCreatingFolder: Bool = false
    @Published var creatingFolderInlineId: String?

    // Drag and drop state
    @Published var isProcessingDrop: Bool = false
    @Published var dropProgress: Double = 0.0
    @Published var dropErrorMessage: String?
    @Published var dropSuccessCount: Int = 0
    @Published var dropFailureCount: Int = 0

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

/// Global sidebar state manager - tracks state for each window
@MainActor
class SidebarStateManager {
    static let shared = SidebarStateManager()

    private var windowStates: [String: SidebarState] = [:]

    private init() {}

    /// Get or create sidebar state for a window
    func state(for windowId: String) -> SidebarState {
        if let existing = windowStates[windowId] {
            return existing
        }

        let newState = SidebarState(windowId: windowId)
        windowStates[windowId] = newState
        return newState
    }

    /// Remove state for a closed window
    func removeState(for windowId: String) {
        windowStates.removeValue(forKey: windowId)
    }
}
