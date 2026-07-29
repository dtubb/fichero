import Observation
import SwiftUI

/// Manages sidebar state with persistence across app relaunches
/// Stores expansion states per window
@MainActor
@Observable
class SidebarState {
    // MARK: - Persisted State (saved to UserDefaults)

    /// Individual item expansion states (folder/library headers)
    ///
    /// The `didSet` guards on a real change for the same reason
    /// `purgeRetiredDefaults` is guarded (#4104): a `UserDefaults.set` posts
    /// `didChangeNotification` whether or not the value differs, and that
    /// notification invalidates every `@AppStorage`/`@SceneStorage` in the
    /// window. SwiftUI writes back through this binding on paths that do not
    /// change it (`reset()` on already-clean state, a disclosure binding
    /// re-committing the same set), so an unguarded write put an
    /// AttributeGraph invalidation on the click path for free.
    var expandedItems: Set<String> {
        didSet {
            guard expandedItems != oldValue else { return }
            saveExpandedItems()
        }
    }

    /// Library expansion states (library ID -> expanded)
    var libraryExpansionStates: [String: Bool] {
        didSet {
            guard libraryExpansionStates != oldValue else { return }
            saveLibraryExpansionStates()
        }
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
    /// A selected alias whose target no longer exists (dangling, #2591).
    var aliasErrorMessage: String?
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
        if let saved = EngineConfig.defaults.array(forKey: itemsKey) as? [String] {
            self.expandedItems = Set(saved)
        } else {
            self.expandedItems = []
        }

        // Load persisted library expansion states (default: all expanded)
        let libKey = "sidebar.libraries.\(windowId)"
        if let saved = EngineConfig.defaults.dictionary(forKey: libKey) as? [String: Bool] {
            self.libraryExpansionStates = saved
        } else {
            self.libraryExpansionStates = [:]
        }

        // Purge stale persistence from the retired unified-section headers
        // (removed when the per-library sub-sections collapsed into one node list).
        Self.purgeRetiredDefaults(windowId: windowId)
    }

    /// One-time purge of the retired unified-section key. MUST stay guarded:
    /// this init runs on every `SidebarView.init` (`State(wrappedValue:)` is
    /// re-evaluated each parent body pass), and an unconditional
    /// `removeObject` posts `UserDefaults.didChangeNotification` even when
    /// the key is absent — which invalidates every @AppStorage/@SceneStorage
    /// in the window and spun the AttributeGraph at 100% CPU (#4104).
    @discardableResult
    static func purgeRetiredDefaults(
        windowId: String,
        defaults: UserDefaults = EngineConfig.defaults
    ) -> Bool {
        let key = "sidebar.unified.sections.\(windowId)"
        guard defaults.object(forKey: key) != nil else { return false }
        defaults.removeObject(forKey: key)
        return true
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
        aliasErrorMessage = nil
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
        EngineConfig.defaults.set(Array(expandedItems), forKey: expandedItemsKey)
    }

    private func saveLibraryExpansionStates() {
        EngineConfig.defaults.set(libraryExpansionStates, forKey: libraryExpansionKey)
    }
}
