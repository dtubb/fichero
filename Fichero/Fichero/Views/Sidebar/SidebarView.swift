import SwiftUI
import UniformTypeIdentifiers
import OSLog
import Combine

/// Structured logger for sidebar operations
private let logger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

/// Universal Sidebar showing all open libraries
/// Each library contains all its items (documents, searches, chats, workflows)
struct SidebarView: View {
    @Binding var viewMode: AppViewMode
    @Binding var selectedItemId: String?

    // LibraryManager - shows all open libraries
    @ObservedObject var libraryManager: LibraryManager

    // Window state - needed to switch libraries when selecting items
    @EnvironmentObject var windowState: WindowState

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Item type registry for extensible item creation (injected from ContentView)
    @ObservedObject var itemRegistry: ItemTypeRegistry

    // SidebarState for expansion persistence
    @StateObject private var sidebarState = SidebarState()

    // Cached sidebar items - rebuilt when service data changes (via Combine observers)
    @State private var cachedLibraryHeaders: [SidebarItem] = []

    // Store Combine subscriptions
    @State private var cancellables = Set<AnyCancellable>()

    /// All cached items combined (for recursive searches)
    private var allCachedItems: [SidebarItem] {
        cachedLibraryHeaders
    }

    /// Derive the selected SidebarItem from the ID
    private var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        return findItemById(id, in: allCachedItems)
    }

    /// Rebuild all sidebar item caches from ALL libraries
    private func rebuildCaches() {
        var libraryHeaders: [SidebarItem] = []

        for library in libraryManager.openLibraries {
            let libraryContent = SidebarItemBuilder.buildLibraryGroup(library: library)
            let header = SidebarItem.libraryHeader(library: library, children: libraryContent)
            libraryHeaders.append(header)
        }

        cachedLibraryHeaders = libraryHeaders
    }

    /// Get library that owns the selected item
    private var selectedItemLibrary: LibraryManager.LibraryReference? {
        guard let item = selectedItem, let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    /// Recursively find an item by ID
    private func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
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

    // Rename and delete state
    @StateObject private var renameState = RenameStateManager()
    @StateObject private var deleteState = DeleteStateManager()

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
            .sidebarFocusedValues(config: SidebarFocusedValuesConfig(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem,
                createSearch: createNewSearch,
                createChat: createNewChat,
                createWorkflow: createNewWorkflow
            ))
            .sidebarDeleteAlerts(
                deleteState: deleteState,
                performDelete: performDelete
            )
    }

    /// Set up observers for all library services using Combine
    private func setupServiceObservers() {
        // Cancel existing subscriptions
        cancellables.removeAll()

        // Observe changes in all libraries' services
        for library in libraryManager.openLibraries {
            // Observe document changes
            library.documentStore.objectWillChange
                .sink { _ in
                    Task { @MainActor in
                        rebuildCaches()
                    }
                }
                .store(in: &cancellables)

            // Observe saved search changes
            library.savedSearchService.objectWillChange
                .sink { _ in
                    Task { @MainActor in
                        rebuildCaches()
                    }
                }
                .store(in: &cancellables)

            // Observe conversation changes
            library.conversationService.objectWillChange
                .sink { _ in
                    Task { @MainActor in
                        rebuildCaches()
                    }
                }
                .store(in: &cancellables)

            // Observe workflow changes
            library.workflowStore.objectWillChange
                .sink { _ in
                    Task { @MainActor in
                        rebuildCaches()
                    }
                }
                .store(in: &cancellables)
        }
    }

    /// Configure item registry handlers
    private func setupItemRegistry() {
        itemRegistry.createFolder = handleCreateNewFolder
        itemRegistry.importFiles = importFiles
        itemRegistry.createSearch = createNewSearch
        itemRegistry.createChat = createNewChat
        itemRegistry.createWorkflow = createNewWorkflow
    }
}

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        VStack(spacing: 0) {
            List(selection: $selectedItemId) {
                // Render all library headers with their content
                ForEach(cachedLibraryHeaders) { libraryHeader in
                    libraryItemView(libraryHeader)
                }
            }

            SidebarBottomToolbar(
                createSearch: createNewSearch,
                createChat: createNewChat,
                createWorkflow: createNewWorkflow,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles
            )
        }
    }

    /// Render a library header and its contents
    @ViewBuilder
    private func libraryItemView(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId {
            // Global library renders inline without header
            if libraryId == LibraryManager.globalLibraryId {
                renderLibraryItems(libraryHeader.children ?? [])
            } else {
                // Regular libraries use DisclosureGroup
                DisclosureGroup(
                    isExpanded: Binding(
                        get: { sidebarState.isLibraryExpanded(libraryId) },
                        set: { _ in sidebarState.toggleLibraryExpansion(for: libraryId) }
                    )
                ) {
                    renderLibraryItems(libraryHeader.children ?? [])
                } label: {
                    Text(libraryHeader.name)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(Color(red: 0xA9/255, green: 0xA9/255, blue: 0xAC/255))
                }
            }
        }
    }

    /// Render library items with separator between documents and other types
    @ViewBuilder
    private func renderLibraryItems(_ items: [SidebarItem]) -> some View {
        // Separate documents/folders from searches/chats/workflows
        let documents = items.filter { item in
            if case .document = item.itemType { return true }
            if case .folder = item.itemType { return true }
            return false
        }
        let others = items.filter { item in
            if case .savedSearch = item.itemType { return true }
            if case .conversation = item.itemType { return true }
            if case .workflow = item.itemType { return true }
            return false
        }

        // Render documents first
        ForEach(documents) { item in
            SidebarItemRow(
                item: item,
                allCachedItems: allCachedItems,
                expandedItems: Binding(
                    get: { sidebarState.expandedItems },
                    set: { sidebarState.expandedItems = $0 }
                ),
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager
            )
            .tag(item.id)
        }

        // Add separator if we have both documents and other items
        if !documents.isEmpty && !others.isEmpty {
            Divider()
                .padding(.vertical, 4)
        }

        // Render searches, chats, workflows
        ForEach(others) { item in
            SidebarItemRow(
                item: item,
                allCachedItems: allCachedItems,
                expandedItems: Binding(
                    get: { sidebarState.expandedItems },
                    set: { sidebarState.expandedItems = $0 }
                ),
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager
            )
            .tag(item.id)
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
    private func createNewSearch() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                // Use saveSearch API with query parameter
                let savedSearch = try await globalLibrary.savedSearchService.saveSearch(
                    query: "New Search",
                    isSmartSearch: true
                )

                // Reload searches to get updated list
                try await globalLibrary.savedSearchService.loadSavedSearches()
                rebuildCaches()

                // Select the new search
                selectedItemId = "search:\(savedSearch.id)"
                let newSearch = SavedSearch(
                    id: savedSearch.id,
                    name: savedSearch.query,
                    query: savedSearch.query,
                    isSmartSearch: savedSearch.isSmartSearch,
                    folderPath: savedSearch.folderPath,
                    sortOrder: savedSearch.sortOrderInt
                )
                viewMode = .search(newSearch)
            } catch {
                logger.error("Failed to create search: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new chat - defaults to Global library
    private func createNewChat() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                // Create a new conversation by sending an initial message
                // The backend will create the conversation automatically
                let response = try await globalLibrary.chatService.chat(
                    message: "Hello",
                    conversationId: nil,
                    documentIds: nil
                )

                // Reload conversations to get the new one
                try await globalLibrary.conversationService.loadConversations()
                rebuildCaches()

                // Find the conversation we just created
                if let newConv = globalLibrary.conversationService.conversations.first(where: { $0.id == response.conversationId }) {
                    selectedItemId = "conversation:\(newConv.id)"
                    viewMode = .chat(newConv)
                    logger.info("Created new chat: \(newConv.id)")
                }
            } catch {
                logger.error("Failed to create chat: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new workflow - defaults to Global library
    private func createNewWorkflow() {
        guard let globalLibrary = libraryManager.globalLibrary else {
            logger.error("Global library not available")
            return
        }

        Task {
            do {
                // Create a new empty workflow
                let newWorkflowDef = WorkflowDefinition(
                    id: UUID().uuidString,
                    name: "New Workflow",
                    description: "",
                    provider: "",
                    model: "",
                    nodes: [],
                    edges: []
                )

                let response = try await globalLibrary.workflowService.createWorkflow(newWorkflowDef)

                // Reload workflows to get the new one
                await globalLibrary.workflowStore.loadWorkflows()
                rebuildCaches()

                // Create a workflow item and select it
                let workflowItem = WorkflowSidebarItem(
                    id: response.id,
                    name: response.name,
                    description: response.description,
                    nodeCount: response.nodes.count
                )

                selectedItemId = "workflow:\(workflowItem.id)"
                viewMode = .workflow(workflowItem)
                logger.info("Created new workflow: \(workflowItem.id)")
            } catch {
                logger.error("Failed to create workflow: \(error.localizedDescription)")
            }
        }
    }

    /// Create a new folder - defaults to Global library
    private func handleCreateNewFolder() {
        guard libraryManager.globalLibrary != nil else {
            logger.error("Global library not available")
            return
        }

        // Show folder creation dialog
        sidebarState.showingNewFolderDialog = true
        sidebarState.newFolderCategory = .folder
        // Implementation would show a dialog to create folder
    }
}

// MARK: - Import/Delete/Rename

extension SidebarView {
    /// Import files to the library that owns the selected item (or Global if none)
    private func importFiles() {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard let library = targetLibrary else {
            logger.error("No library available for import")
            return
        }

        // Implementation: Show file picker and import to library
        logger.info("Import to library: \(library.displayName)")
    }

    /// Rename the selected item
    private func handleRenameSelectedItem() {
        guard let item = selectedItem else { return }
        renameState.startRename(itemId: item.id, currentName: item.name)
    }

    /// Delete the selected item
    private func handleDeleteSelectedItem() {
        guard let item = selectedItem else { return }

        switch item.itemType {
        case .libraryHeader:
            logger.warning("Cannot delete library header")
        default:
            deleteState.showDeleteConfirmation(for: item)
        }
    }

    /// Perform the actual deletion
    private func performDelete(item: SidebarItem) async {
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
                try await library.savedSearchService.deleteSavedSearch(search.id)
            case .conversation(let conversation):
                try await library.conversationService.deleteConversation(conversation.id)
            case .workflow(let workflow):
                try await library.workflowService.deleteWorkflow(workflow.id)
            case .folder:
                logger.info("Folder deletion not yet implemented")
            case .libraryHeader:
                logger.warning("Cannot delete library header")
            }

            rebuildCaches()
            selectedItemId = nil
        } catch {
            logger.error("Failed to delete item: \(error.localizedDescription)")
        }
    }
}

// NOTE: RenameStateManager, DeleteStateManager, and SidebarConstants
// are defined in separate files (SidebarStateManagers.swift, SidebarConstants.swift)
