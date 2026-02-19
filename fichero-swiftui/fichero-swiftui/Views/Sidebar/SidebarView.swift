import SwiftUI
import UniformTypeIdentifiers
import OSLog
import Combine

/// Structured logger for sidebar operations
private let logger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

// MARK: - Automation Refresh Environment Key

/// Environment key for automation refresh callback (used by editor views to trigger sidebar refresh)
private struct AutomationRefreshKey: EnvironmentKey {
    nonisolated(unsafe) static let defaultValue: (() -> Void)? = nil
}

extension EnvironmentValues {
    /// Callback to refresh automation data (schedules and triggers)
    var automationRefresh: (() -> Void)? {
        get { self[AutomationRefreshKey.self] }
        set { self[AutomationRefreshKey.self] = newValue }
    }
}

/// Universal Sidebar with Xcode-style mode switching
/// Mode bar at top, content changes based on selected mode
/// Each mode shows content grouped by library
struct SidebarView: View {
    @Binding var sidebarMode: SidebarMode
    @Binding var viewMode: AppViewMode
    @Binding var selectedItemId: String?

    // LibraryManager - shows all open libraries
    @ObservedObject var libraryManager: LibraryManager

    // Window state - needed to switch libraries when selecting items
    @EnvironmentObject var windowState: WindowState

    // API client for service calls
    @EnvironmentObject var apiClient: APIClient

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Item type registry for extensible item creation (injected from ContentView)
    @ObservedObject var itemRegistry: ItemTypeRegistry

    // SidebarState for expansion persistence (internal for extension access)
    @StateObject var sidebarState = SidebarState()

    // Rename and delete state (internal for extension access)
    @StateObject var renameState = RenameStateManager()
    @StateObject var deleteState = DeleteStateManager()

    // Cached sidebar items - rebuilt when service data changes (via Combine observers)
    @State var cachedLibraryHeaders: [SidebarItem] = []

    // Chain service for workflows sidebar (global - not per-library yet)
    @StateObject var chainService: ChainService

    // Chains loaded from ChainService
    @State var chains: [WorkflowChain] = []

    // Automation data (schedules and triggers)
    @State var schedules: [ScheduleInfo] = []
    @State var triggers: [TriggerInfo] = []
    @State var automationIsLoading = false

    // Batch data
    @State var batches: [BatchInfo] = []
    @State var batchesIsLoading = false

    // Activity data (historical runs)
    @State var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State var activityIsLoading = false

    // Store Combine subscriptions
    @State var cancellables = Set<AnyCancellable>()

    init(
        sidebarMode: Binding<SidebarMode>,
        viewMode: Binding<AppViewMode>,
        selectedItemId: Binding<String?>,
        libraryManager: LibraryManager,
        itemRegistry: ItemTypeRegistry,
        apiClient: APIClient,
        onCreateChatWithDocuments: (([String]) -> Void)? = nil
    ) {
        self._sidebarMode = sidebarMode
        self._viewMode = viewMode
        self._selectedItemId = selectedItemId
        self.libraryManager = libraryManager
        self.itemRegistry = itemRegistry
        self.onCreateChatWithDocuments = onCreateChatWithDocuments
        // Initialize ChainService with apiClient
        self._chainService = StateObject(wrappedValue: ChainService(apiClient: apiClient))
    }

    /// All cached items combined (for recursive searches)
    var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    /// Derive the selected SidebarItem from the ID
    var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        return findItemById(id, in: allCachedItems)
    }

    /// Rebuild all sidebar item caches from ALL libraries
    func rebuildCaches() {
        var libraryHeaders: [SidebarItem] = []

        for library in libraryManager.openLibraries {
            let libraryContent = SidebarItemBuilder.buildLibraryGroup(library: library)
            let header = SidebarItem.libraryHeader(library: library, children: libraryContent)
            libraryHeaders.append(header)
        }

        cachedLibraryHeaders = libraryHeaders
    }

    /// Get library that owns the selected item
    var selectedItemLibrary: LibraryManager.LibraryReference? {
        guard let item = selectedItem, let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    /// Recursively find an item by ID
    func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if item.id == id {
                return item
            }
            if let children = item.children,
               let found = findItemById(id, in: children) {
                return found
            }
        }
        return nil
    }

    var body: some View {
        sidebarContent
            .sidebarStyle()
            .task {
                // Check cancellation before starting
                guard !Task.isCancelled else { return }

                // Build initial caches
                rebuildCaches()

                guard !Task.isCancelled else { return }

                // Subscribe to all library service changes
                setupServiceObservers()

                // Configure item registry handlers
                setupItemRegistry()

                guard !Task.isCancelled else { return }

                // Load chains for workflows sidebar
                await chainService.loadChains()

                guard !Task.isCancelled else { return }

                // Load automation data (schedules and triggers)
                await loadAutomationData()
            }
            .onChange(of: selectedItemId) { _, newId in
                // Handle selection changes
                logger.info("selectedItemId changed to: \(newId ?? "nil")")
                if let id = newId {
                    let item = findItemById(id, in: allCachedItems)
                    handleSelection(item)
                }
            }
            .onChange(of: libraryManager.openLibraries.count) { _, _ in
                // Rebuild when libraries are added/removed
                rebuildCaches()

                // Resubscribe to service changes for new libraries
                setupServiceObservers()
            }
            .onChange(of: sidebarMode) { _, newMode in
                // Refresh data when switching to mode-specific sidebars
                // This ensures sidebar shows updated data after editor saves
                if newMode == .automation {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadAutomationData()
                    }
                } else if newMode == .batches {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadBatchData()
                    }
                } else if newMode == .activity {
                    Task {
                        guard !Task.isCancelled else { return }
                        await loadActivityData()
                    }
                }
            }
            .sidebarFocusedValues(config: SidebarFocusedValuesConfig(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem,
                createSearch: createNewSearch,
                createChat: createNewChat,
                createWorkflow: createNewWorkflow,
                createChain: createNewChain,
                createComparison: createNewComparison,
                createSchedule: createNewSchedule,
                createTrigger: createNewTrigger
            ))
            .sidebarDeleteAlerts(
                deleteState: deleteState,
                performDelete: performDelete
            )
            .sidebarNewFolderDialog(
                sidebarState: sidebarState,
                createFolder: createFolder
            )
            .sidebarFileImporter(
                isPresented: $sidebarState.showingFileImporter,
                importFiles: handleImportedFiles
            )
    }
}

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        VStack(spacing: 0) {
            // Mode bar at top (Xcode-style)
            SidebarModeBar(selectedMode: $sidebarMode)

            Divider()

            // Content based on selected mode
            modeContent

            // Bottom toolbar (only show for content creation modes)
            if shouldShowBottomToolbar {
                Divider()
                SidebarBottomToolbar(
                    createSearch: createNewSearch,
                    createChat: createNewChat,
                    createWorkflow: createNewWorkflow,
                    createFolder: handleCreateNewFolder,
                    importFiles: importFiles,
                    createComparison: createNewComparison,
                    createSchedule: createNewSchedule,
                    createTrigger: createNewTrigger
                )
            }
        }
    }

    /// Whether to show the bottom toolbar (only for content modes)
    private var shouldShowBottomToolbar: Bool {
        switch sidebarMode {
        case .library, .search, .chat, .workflows, .automation:
            return true
        case .batches, .activity:
            return false
        }
    }

    /// Content view based on selected sidebar mode
    @ViewBuilder
    private var modeContent: some View {
        switch sidebarMode {
        case .library:
            LibrarySidebarContent(
                selectedItemId: $selectedItemId,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .search:
            SearchSidebarContent(
                selectedItemId: $selectedItemId,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .chat:
            ChatSidebarContent(
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarMode: $sidebarMode,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders
            )

        case .workflows:
            WorkflowsSidebarContent(
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                cachedLibraryHeaders: cachedLibraryHeaders,
                chains: chains,
                chainService: chainService
            )

        case .batches:
            BatchesSidebarContent(
                libraryManager: libraryManager,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                batches: batches,
                isLoading: batchesIsLoading,
                onRefresh: { Task { await loadBatchData() } }
            )

        case .automation:
            AutomationSidebarContent(
                libraryManager: libraryManager,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                sidebarState: sidebarState,
                renameState: renameState,
                deleteState: deleteState,
                schedules: schedules,
                triggers: triggers,
                isLoading: automationIsLoading,
                onRefresh: { Task { await loadAutomationData() } }
            )

        case .activity:
            ActivitySidebarContent(
                libraryManager: libraryManager,
                sidebarState: sidebarState,
                selectedItemId: $selectedItemId,
                viewMode: $viewMode,
                historicalRunsByLibrary: historicalRunsByLibrary,
                isLoading: activityIsLoading,
                onRefresh: { Task { await loadActivityData() } }
            )
        }
    }
}

// MARK: - Selection Handling

extension SidebarView {
    /// Handle sidebar item selection and update view mode
    private func handleSelection(_ item: SidebarItem?) {
        guard let item = item else {
            logger.info("handleSelection called with nil item")
            return
        }

        logger.info("handleSelection: \(item.name) (category: \(item.category.rawValue), type: \(String(describing: item.itemType)))")

        // Switch window's library if the selected item belongs to a different library
        if let itemLibraryId = item.libraryId, itemLibraryId != windowState.libraryId {
            logger.info("Switching window from library \(windowState.libraryId) to library \(itemLibraryId)")
            windowState.libraryId = itemLibraryId
            // Wait for next run loop to allow SwiftUI to update environment objects
            // This ensures the new library's services are injected before we try to use them
        } else {
            logger.info("Item belongs to current library: \(windowState.libraryId)")
        }

        // Update view mode based on item type
        switch item.itemType {
        case .document(let doc):
            logger.info("Switching to library view with document: \(doc.name)")
            viewMode = .library(doc)
        case .savedSearch(let search):
            logger.info("Switching to search view with search: \(search.name)")
            viewMode = .search(search)
        case .conversation(let conversation):
            logger.info("Switching to chat view with conversation: \(conversation.id)")
            viewMode = .chat(conversation)
        case .workflow(let workflow):
            logger.info("Switching to workflow view with workflow: \(workflow.name)")
            viewMode = .workflow(workflow)
        case .chain, .comparison, .schedule, .trigger, .batch, .activityRun:
            // These item types are handled by their specialized sidebar modes
            logger.info("Item type \(item.category.rawValue) clicked - detail views handled by mode sidebar")
        case .folder:
            // Check if this is a category folder (Search, Chat, Workflow)
            // and switch to that view mode even if empty
            logger.info("Folder clicked: category = \(item.category.rawValue)")
            switch item.category {
            case .search:
                logger.info("Switching to empty search view")
                viewMode = .search(nil)
            case .chat:
                logger.info("Switching to empty chat view")
                viewMode = .chat(nil)
            case .workflow:
                logger.info("Switching to empty workflow view")
                viewMode = .workflow(nil)
                case .automation, .batch, .activity:
                // Automation-related folders
                logger.info("Automation folder - just toggling expansion")
                case .folder, .library:
                // Regular folders just toggle expansion
                logger.info("Regular folder - just toggling expansion")
            }
            case .libraryHeader:
            // Library headers just toggle expansion
            logger.info("Library header clicked - just toggling expansion")
        }
    }
}

// NOTE: RenameStateManager, DeleteStateManager, and SidebarConstants
// are defined in separate files (SidebarStateManagers.swift, SidebarConstants.swift)
// Creation handlers are in SidebarCreationHandlers.swift
// Import/Delete/Rename actions are in SidebarActions.swift
// Service observers and data loading are in SidebarObservers.swift
