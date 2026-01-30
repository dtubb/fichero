import SwiftUI
import UniformTypeIdentifiers
import OSLog
import Combine

/// Structured logger for sidebar operations
private let logger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

// MARK: - Automation Refresh Environment Key

/// Environment key for automation refresh callback (used by editor views to trigger sidebar refresh)
private struct AutomationRefreshKey: EnvironmentKey {
    static let defaultValue: (() -> Void)? = nil
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
    @StateObject private var chainService: ChainService

    // Chains loaded from ChainService
    @State private var chains: [WorkflowChain] = []

    // Automation data (schedules and triggers)
    @State private var schedules: [ScheduleInfo] = []
    @State private var triggers: [TriggerInfo] = []
    @State private var automationIsLoading = false

    // Batch data
    @State private var batches: [BatchInfo] = []
    @State private var batchesIsLoading = false

    // Activity data (historical runs)
    @State private var historicalRunsByLibrary: [UUID: [ActivityItem]] = [:]
    @State private var activityIsLoading = false

    // Store Combine subscriptions
    @State private var cancellables = Set<AnyCancellable>()

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

    /// Set up observers for all library services using Combine
    /// Uses $property publishers (not objectWillChange) to ensure we read AFTER mutations complete
    private func setupServiceObservers() {
        // Cancel existing subscriptions
        cancellables.removeAll()

        // Observe changes in all libraries' services
        for library in libraryManager.openLibraries {
            // Observe document changes - use $collections which fires AFTER mutation
            library.documentStore.$collections
                .dropFirst()  // Skip initial value
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe saved search changes
            library.savedSearchServiceGenerated.$savedSearches
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe conversation changes
            library.conversationServiceGenerated.$conversations
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)

            // Observe workflow changes - use $workflows which fires AFTER mutation
            library.workflowStore.$workflows
                .dropFirst()
                .receive(on: RunLoop.main)
                .sink { _ in rebuildCaches() }
                .store(in: &cancellables)
        }

        // Observe chain changes (global ChainService)
        chainService.$chains
            .dropFirst()
            .receive(on: RunLoop.main)
            .sink { newChains in
                chains = newChains
            }
            .store(in: &cancellables)
    }

    /// Load automation data (schedules and triggers)
    private func loadAutomationData() async {
        guard !automationIsLoading else { return }
        automationIsLoading = true
        defer { automationIsLoading = false }

        do {
            guard let library = libraryManager.openLibraries.first else {
                logger.warning("No library available to load automation data")
                return
            }
            let automationService = library.automationService
            async let schedulesTask: [ScheduleInfo] = automationService.listSchedules(limit: 100)
            async let triggersTask: [TriggerInfo] = automationService.listTriggers(limit: 100)

            let (loadedSchedules, loadedTriggers) = try await (schedulesTask, triggersTask)
            schedules = loadedSchedules
            triggers = loadedTriggers
            logger.info("Loaded \(loadedSchedules.count) schedules and \(loadedTriggers.count) triggers")
        } catch {
            logger.error("Failed to load automation data: \(error.localizedDescription)")
        }
    }

    /// Load batch data
    private func loadBatchData() async {
        guard !batchesIsLoading else { return }
        batchesIsLoading = true
        defer { batchesIsLoading = false }

        do {
            guard let library = libraryManager.openLibraries.first else {
                logger.warning("No library available for loading batches")
                return
            }
            batches = try await library.batchService.listBatchesAsInfo(status: nil, limit: 100)
            logger.info("Loaded \(batches.count) batches")
        } catch {
            logger.error("Failed to load batch data: \(error.localizedDescription)")
        }
    }

    /// Load activity data (historical workflow runs)
    private func loadActivityData() async {
        guard !activityIsLoading else { return }
        activityIsLoading = true
        defer { activityIsLoading = false }

        let types = [
            "workflow_completed",
            "workflow_failed",
            "workflow_cancelled"
        ]
        let since = Date().addingTimeInterval(-7 * 24 * 3600)

        // Load activity from each open library
        for library in libraryManager.openLibraries {
            guard !Task.isCancelled else { return }

            do {
                let activityService = library.activityService
                let runs = try await activityService.queryActivities(
                    types: types,
                    since: since,
                    limit: 100
                )

                guard !Task.isCancelled else { return }

                historicalRunsByLibrary[library.id] = runs
                logger.info("Loaded \(runs.count) activity items from \(library.displayName)")
            } catch {
                logger.error("Failed to load activity from \(library.displayName): \(error.localizedDescription)")
            }
        }
    }

    /// Configure item registry handlers
    private func setupItemRegistry() {
        itemRegistry.createFolder = handleCreateNewFolder
        itemRegistry.importFiles = {
            importFiles(mode: .link)  // Default to link mode from Add menu
        }
        itemRegistry.createSearch = createNewSearch
        itemRegistry.createChat = createNewChat
        itemRegistry.createComparison = createNewComparison
        itemRegistry.createWorkflow = createNewWorkflow
        itemRegistry.createChain = createNewChain
        itemRegistry.createSchedule = createNewSchedule
        itemRegistry.createTrigger = createNewTrigger
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
                break
            case .folder, .library:
                // Regular folders just toggle expansion
                logger.info("Regular folder - just toggling expansion")
                break
            }
        case .libraryHeader:
            // Library headers just toggle expansion
            logger.info("Library header clicked - just toggling expansion")
            break
        }
    }
}

// MARK: - Creation Methods

extension SidebarView {
    /// Create a new search - defaults to Global library
    func createNewSearch() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                let savedSearch = try await globalLibrary.savedSearchServiceGenerated.saveSearch(
                    query: "New Search",
                    isSmartSearch: true
                )
                try await globalLibrary.savedSearchServiceGenerated.loadSavedSearches()
                rebuildCaches()
                selectedItemId = "search:\(savedSearch.id)"
                let newSearch = SavedSearch(
                    id: savedSearch.id,
                    name: savedSearch.query,
                    query: savedSearch.query,
                    isSmartSearch: savedSearch.isSmartSearch,
                    folderPath: savedSearch.folderPath,
                    sortOrder: savedSearch.sortOrder
                )
                sidebarMode = .search  // Switch to search sidebar
                viewMode = .search(newSearch)
            } catch {
                logger.error("Failed to create search: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new chat - defaults to Global library
    func createNewChat() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                let response = try await globalLibrary.chatServiceGenerated.chat(
                    message: "Hello",
                    conversationId: nil,
                    documentIds: nil
                )

                // Create conversation directly from response (don't rely on lookup which may have timing issues)
                let newConv = Conversation(
                    id: response.conversationId,
                    title: "New Chat",
                    messages: [
                        ChatMessage(role: .user, content: "Hello"),
                        ChatMessage(role: .assistant, content: response.message)
                    ],
                    documentScope: [],
                    folderPath: "/",
                    sortOrder: 0
                )

                // Add to service's conversations array
                globalLibrary.conversationServiceGenerated.conversations.append(newConv)

                // Rebuild caches so sidebar shows the new chat
                rebuildCaches()

                // Select the new chat
                selectedItemId = "chat:\(newConv.id)"
                sidebarMode = .chat  // Switch to chat sidebar
                viewMode = .chat(newConv)
                logger.info("Created new chat: \(newConv.id)")

            } catch {
                logger.error("Failed to create chat: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new workflow - defaults to Global library
    func createNewWorkflow() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                let newWorkflowDef = WorkflowDefinition(
                    id: UUID().uuidString,
                    name: "New Workflow",
                    description: "",
                    provider: "",
                    model: "",
                    nodes: [],
                    edges: [],
                    folderPath: "/",
                    sortOrder: 0
                )
                let response = try await globalLibrary.workflowServiceGenerated.createWorkflow(newWorkflowDef)
                await globalLibrary.workflowStore.loadWorkflows()
                rebuildCaches()
                let workflowItem = WorkflowSidebarItem(
                    id: response.id,
                    name: response.name,
                    description: response.description,
                    nodeCount: response.nodes.count,
                    isEnabled: true,
                    folderPath: response.folderPath,
                    sortOrder: response.sortOrder,
                    createdAt: Date(),
                    updatedAt: Date()
                )
                selectedItemId = "workflow:\(workflowItem.id)"
                sidebarMode = .workflows  // Switch to workflows sidebar
                viewMode = .workflow(workflowItem)
                logger.info("Created new workflow: \(workflowItem.id)")
            } catch {
                logger.error("Failed to create workflow: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new folder - defaults to Global library
    func handleCreateNewFolder() {
        guard libraryManager.globalLibrary != nil else {
            logger.error("Global library not available")
            return
        }
        sidebarState.showingNewFolderDialog = true
        sidebarState.newFolderCategory = .folder
    }

    /// Create a new chain via ChainService
    func createNewChain() {
        logger.info("Creating new chain")
        Task {
            do {
                let chainService = ChainService(apiClient: apiClient)
                let newChain = try await chainService.createChain(
                    name: "New Chain",
                    description: "",
                    steps: []
                )

                // Switch to workflows mode and select the new chain
                sidebarMode = .workflows
                selectedItemId = "chain-\(newChain.id)"  // Match the tag format in WorkflowsSidebarContent
                viewMode = .chain(newChain)
                logger.info("Created new chain: \(newChain.id)")
            } catch {
                logger.error("Failed to create chain: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new comparison - opens the comparison view
    func createNewComparison() {
        logger.info("Creating new comparison")
        sidebarMode = .chat
        viewMode = .comparison(nil)
    }

    /// Create a new schedule - shows the schedule creation sheet
    func createNewSchedule() {
        logger.info("Creating new schedule")
        sidebarMode = .automation
        sidebarState.showingScheduleCreation = true
    }

    /// Create a new trigger - shows the trigger creation sheet
    func createNewTrigger() {
        logger.info("Creating new trigger")
        sidebarMode = .automation
        sidebarState.showingTriggerCreation = true
    }

    /// Actually create the folder after user enters name
    func createFolder(_ name: String) async {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard let library = targetLibrary else {
            sidebarState.newFolderErrorMessage = "No library available"
            return
        }
        logger.info("Creating folder '\(name)' in library: \(library.displayName)")
        do {
            _ = try await library.documentStore.createCollection(name: name)
            logger.info("Created folder: \(name)")
            rebuildCaches()
        } catch {
            logger.error("Failed to create folder: \(error)")
            sidebarState.newFolderErrorMessage = error.localizedDescription
        }
    }
}

// MARK: - Import/Delete/Rename

extension SidebarView {
    /// Import files to the library that owns the selected item (or Global if none)
    func importFiles(mode: IngestMode = .link) {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard targetLibrary != nil else {
            logger.error("No library available for import")
            return
        }
        sidebarState.selectedImportMode = mode
        sidebarState.showingFileImporter = true
    }

    /// Handle imported files from file picker
    func handleImportedFiles(_ urls: [URL]) async {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard let library = targetLibrary else {
            logger.error("No library available for import")
            return
        }
        let mode = sidebarState.selectedImportMode
        logger.info("Importing \(urls.count) files to library: \(library.displayName)")
        do {
            _ = try await library.importService.importFiles(urls, mode: mode)
            logger.info("Imported \(urls.count) files using mode: \(mode.rawValue)")
        } catch {
            logger.error("Failed to import files: \(error)")
        }
        await library.documentStore.refresh()
        rebuildCaches()
    }

    /// Rename the selected item
    func handleRenameSelectedItem() {
        guard let item = selectedItem else { return }
        renameState.startRename(itemId: item.id, currentName: item.name)
    }

    /// Delete the selected item
    func handleDeleteSelectedItem() {
        guard let item = selectedItem else { return }
        switch item.itemType {
        case .libraryHeader:
            logger.warning("Cannot delete library header")
        default:
            deleteState.showDeleteConfirmation(for: item)
        }
    }

    /// Perform the actual deletion
    func performDelete(item: SidebarItem) async {
        logger.info("performDelete for: \(item.name)")
        guard let libraryId = item.libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else {
            logger.error("Could not find library for deletion")
            return
        }
        do {
            switch item.itemType {
            case .document(let doc):
                try await library.documentStore.deleteDocument(doc)
            case .savedSearch(let search):
                try await library.savedSearchServiceGenerated.deleteSavedSearch(search.id)
            case .conversation(let conversation):
                try await library.conversationServiceGenerated.deleteConversation(conversation.id)
            case .workflow(let workflow):
                try await library.workflowStore.deleteWorkflow(workflow.id)
            case .chain(let chain):
                try await library.chainService.deleteChain(chain.id)
            case .schedule(let schedule):
                try await library.automationService.deleteSchedule(scheduleId: schedule.scheduleId)
                await loadAutomationData()  // Refresh automation sidebar
            case .trigger(let trigger):
                try await library.automationService.deleteTrigger(triggerId: trigger.triggerId)
                await loadAutomationData()  // Refresh automation sidebar
            case .batch(let batch):
                try await library.batchService.deleteBatch(batchId: batch.batchId)
                await loadBatchData()  // Refresh batches sidebar
            case .comparison, .activityRun:
                logger.warning("This item type cannot be deleted")
            case .folder:
                logger.info("Folder deletion not yet implemented")
            case .libraryHeader:
                logger.warning("Cannot delete library header")
            }
            logger.info("Delete successful")
            rebuildCaches()
            selectedItemId = nil
        } catch {
            logger.error("Failed to delete: \(error.localizedDescription)")
        }
    }
}

// NOTE: RenameStateManager, DeleteStateManager, and SidebarConstants
// are defined in separate files (SidebarStateManagers.swift, SidebarConstants.swift)
