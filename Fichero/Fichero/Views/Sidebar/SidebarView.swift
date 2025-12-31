import SwiftUI
import UniformTypeIdentifiers
import OSLog

/// Structured logger for sidebar operations.
/// Uses subsystem for organization and category for filtering.
private let logger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

/// Sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    @Binding var viewMode: AppViewMode
    @Binding var selectedItemId: String?

    // Observable stores - automatically trigger UI updates when @Published properties change
    @ObservedObject var documentStore: DocumentStore
    @ObservedObject var savedSearchService: SavedSearchService
    @ObservedObject var conversationService: ConversationService
    @ObservedObject var workflowStore: WorkflowStore

    // WindowState to access library information (optional - may not be set in all contexts)
    var windowState: WindowState?

    // LibraryManager for showing all open libraries
    @ObservedObject var libraryManager: LibraryManager = LibraryManager.shared

    // Callback when user switches to a different library
    var onSwitchLibrary: ((UUID) -> Void)?

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Cache for sidebar items - rebuilt only when source data changes
    @State private var cachedLibraryItems: [SidebarItem] = []
    @State private var cachedSearchItems: [SidebarItem] = []
    @State private var cachedChatItems: [SidebarItem] = []
    @State private var cachedWorkflowItems: [SidebarItem] = []

    /// All cached items combined (for circular reference checks)
    /// Flattened list of all sidebar items across all sections.
    /// Used for ID-based lookups and recursive searches.
    private var allCachedItems: [SidebarItem] {
        cachedLibraryItems + cachedSearchItems + cachedChatItems + cachedWorkflowItems
    }

    /// Derive the selected SidebarItem from the ID (uses cached items)
    private var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        return findItemById(id, in: allCachedItems)
    }

    /// Rebuild all sidebar item caches from source data
    private func rebuildCaches() {
        cachedLibraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
        cachedSearchItems = SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
        cachedChatItems = SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
        cachedWorkflowItems = SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
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

    // Expansion state
    @State private var expandedItems: Set<String> = []
    @State private var openLibrariesExpanded = true
    @State private var libraryExpanded = true
    @State private var searchesExpanded = true
    @State private var chatExpanded = true
    @State private var workflowsExpanded = true
    @State private var isChatDropTargeted = false

    // Drop targeting state for section headers
    @State private var isSearchHeaderDropTargeted = false
    @State private var isChatHeaderDropTargeted = false
    @State private var isWorkflowHeaderDropTargeted = false

    // Rename and delete state
    @StateObject private var renameState = RenameStateManager()
    @StateObject private var deleteState = DeleteStateManager()

    var body: some View {
        sidebarContent
            .environmentObject(SidebarServices(
                documentStore: documentStore,
                savedSearchService: savedSearchService,
                conversationService: conversationService,
                workflowStore: workflowStore
            ))
            .sidebarStyle()
            .sidebarToolbar(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem
            )
            .sidebarCacheMonitoring(
                config: SidebarCacheMonitoringConfig(
                    rebuildCaches: rebuildCaches,
                    documentStore: documentStore,
                    savedSearchService: savedSearchService,
                    conversationService: conversationService,
                    workflowStore: workflowStore,
                    selectedItem: selectedItem,
                    handleSelection: handleSelection
                )
            )
            .sidebarFocusedValues(
                selectedItem: selectedItem,
                createFolder: handleCreateNewFolder,
                importFiles: importFiles,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem
            )
            .sidebarDeleteAlerts(
                deleteState: deleteState,
                performDelete: performDelete
            )
    }
}

// MARK: - View Components

extension SidebarView {
    // MARK: - Sidebar Content

    @ViewBuilder
    var sidebarContent: some View {
        List(selection: $selectedItemId) {
            openLibrariesSectionView
            librarySectionView
            searchesSectionView
            chatSectionView
            workflowsSectionView
        }
    }

    // MARK: - Open Libraries Section (DEVONthink-style)

    @ViewBuilder
    private var openLibrariesSectionView: some View {
        Section(isExpanded: $openLibrariesExpanded) {
            ForEach(libraryManager.openLibraries) { library in
                LibraryRow(
                    library: library,
                    isCurrentLibrary: library.id == windowState?.libraryId,
                    onSelect: {
                        onSwitchLibrary?(library.id)
                    }
                )
            }
        } header: {
            SidebarSectionHeader(
                title: "Open Libraries",
                icon: "books.vertical"
            )
        }
    }

    @ViewBuilder
    private var librarySectionView: some View {
        Section(isExpanded: $libraryExpanded) {
            ForEach(cachedLibraryItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: allCachedItems,
                    expandedItems: $expandedItems,
                    renameState: renameState,
                    deleteState: deleteState
                )
                .padding(.leading, SidebarConstants.itemLeadingPadding)
                .tag(item.id)
            }
            .onMove(perform: { _, _ in
                // Handle reordering of library items
                // This would require updating the backend collection order
            })
        } header: {
            SidebarSectionHeader(
                title: windowState?.library?.displayName ?? "Library",
                icon: "folder",
                onDrop: handleDropToRootLevel
            )
        }
    }

    @ViewBuilder
    private var searchesSectionView: some View {
        Section(isExpanded: $searchesExpanded) {
            ForEach(cachedSearchItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: allCachedItems,
                    expandedItems: $expandedItems,
                    renameState: renameState,
                    deleteState: deleteState
                )
                .padding(.leading, SidebarConstants.itemLeadingPadding)
                .tag(item.id)
            }
            .onMove(perform: { _, _ in
                // Handle reordering of search items
            })

            // New Search button
            Button(action: { createNewSearch() }, label: {
                Label("New Search...", systemImage: "plus")
                    .foregroundColor(.secondary)
            })
            .buttonStyle(.plain)
            .padding(.leading, 4)
        } header: {
            SidebarSectionHeader(title: "Searches", icon: "magnifyingglass")
                .background(isSearchHeaderDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
                .cornerRadius(4)
                .dropDestination(for: String.self) { itemIDs, _ in
                    handleSearchHeaderDrop(itemIDs: itemIDs)
                } isTargeted: { isTargeted in
                    isSearchHeaderDropTargeted = isTargeted
                }
        }
    }

    @ViewBuilder
    private var chatSectionView: some View {
        Section(isExpanded: $chatExpanded) {
            ForEach(cachedChatItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: allCachedItems,
                    expandedItems: $expandedItems,
                    renameState: renameState,
                    deleteState: deleteState
                )
                .padding(.leading, SidebarConstants.itemLeadingPadding)
                .tag(item.id)
            }
            .onMove(perform: { _, _ in
                // Handle reordering of chat items
            })

            // New Chat button with drop support
            Button(action: { createNewChat() }, label: {
                HStack {
                    Label("New Chat...", systemImage: "plus")
                        .foregroundColor(isChatDropTargeted ? .accentColor : .secondary)
                    if isChatDropTargeted {
                        Spacer()
                        Image(systemName: "arrow.down.circle.fill")
                            .foregroundColor(.accentColor)
                    }
                }
            })
            .buttonStyle(.plain)
            .padding(.leading, 4)
            .dropDestination(for: String.self) { itemIDs, _ in
                handleChatButtonDrop(itemIDs: itemIDs)
            } isTargeted: { isTargeted in
                isChatDropTargeted = isTargeted
            }
        } header: {
            SidebarSectionHeader(title: "Chat", icon: "bubble.left.and.bubble.right")
                .background(isChatHeaderDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
                .cornerRadius(4)
                .dropDestination(for: String.self) { itemIDs, _ in
                    handleChatHeaderDrop(itemIDs: itemIDs)
                } isTargeted: { isTargeted in
                    isChatHeaderDropTargeted = isTargeted
                }
        }
    }

    @ViewBuilder
    private var workflowsSectionView: some View {
        Section(isExpanded: $workflowsExpanded) {
            ForEach(cachedWorkflowItems) { item in
                SidebarItemRow(
                    item: item,
                    allCachedItems: allCachedItems,
                    expandedItems: $expandedItems,
                    renameState: renameState,
                    deleteState: deleteState
                )
                .padding(.leading, SidebarConstants.itemLeadingPadding)
                .tag(item.id)
            }
            .onMove(perform: { _, _ in
                // Handle reordering of workflow items
            })

            // New Workflow button
            Button(action: { createNewWorkflow() }, label: {
                Label("New Workflow...", systemImage: "plus")
                    .foregroundColor(.secondary)
            })
            .buttonStyle(.plain)
            .padding(.leading, 4)
        } header: {
            SidebarSectionHeader(title: "Workflows", icon: "arrow.triangle.branch")
                .background(isWorkflowHeaderDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
                .cornerRadius(4)
                .dropDestination(for: String.self) { itemIDs, _ in
                    handleWorkflowHeaderDrop(itemIDs: itemIDs)
                } isTargeted: { isTargeted in
                    isWorkflowHeaderDropTargeted = isTargeted
                }
        }
    }

    // MARK: - Actions

    /// Handles sidebar item selection and updates the view mode accordingly.
    /// Maps each item type to its corresponding view mode.
    private func handleSelection(_ item: SidebarItem?) {
        guard let item = item else { return }

        switch item.itemType {
        case .document(let doc):
            viewMode = .library(doc)
        case .savedSearch(let search):
            viewMode = .search(search)
        case .conversation(let conversation):
            viewMode = .chat(conversation)
        case .workflow(let workflow):
            viewMode = .workflow(workflow)
        case .sectionHeader:
            break
        }
    }

    /// Creates a new search and switches to search view mode.
    private func createNewSearch() {
        viewMode = .search(nil)
    }

    /// Creates a new chat conversation and switches to chat view mode.
    private func createNewChat() {
        viewMode = .chat(nil)
    }

    /// Creates a new workflow and switches to workflow view mode.
    private func createNewWorkflow() {
        viewMode = .workflow(nil)
    }

}

// MARK: - SidebarView Action Handlers

private extension SidebarView {
    // MARK: - Menu Command Handlers

    func importFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = true  // Allow selecting folders
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.image, .pdf, .plainText, .data]
        panel.message = "Select files or folders to import"

        if panel.runModal() == .OK {
            // Get parent ID from selected item - only use folders as parents
            var parentId: String?
            if let selected = selectedItem,
               case .document(let doc) = selected.itemType,
               doc.docType == .folder {
                parentId = doc.id
            }

            // Import files and folders
            Task {
                for url in panel.urls {
                    do {
                        var isDirectory: ObjCBool = false
                        FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)

                        if isDirectory.boolValue {
                            // Import folder recursively
                            try await documentStore.importFolder(at: url, parentId: parentId)
                            logger.info("Imported folder: \(url.lastPathComponent)")
                        } else {
                            // Import single file
                            _ = try await documentStore.importFile(at: url, parentId: parentId)
                            logger.info("Imported file: \(url.lastPathComponent)")
                        }
                    } catch {
                        logger.error("Failed to import \(url.lastPathComponent): \(error)")
                    }
                }
                // UI updates automatically via @Published collections
            }
        }
    }

    func handleCreateNewFolder() {
        // Create new folder
        // If an item is selected, create as its child; otherwise create at root
        let parentId: String?
        if let selected = selectedItem,
           case .document(let doc) = selected.itemType,
           doc.docType == .folder {
            parentId = doc.id
        } else {
            parentId = nil
        }

        Task {
            do {
                _ = try await documentStore.createFolder(name: "New Folder", parentId: parentId)
                logger.info("Created new folder with parent: \(parentId ?? "root")")
            } catch {
                logger.error("Failed to create folder: \(error)")
            }
        }
    }

    func handleRenameSelectedItem() {
        guard let selected = selectedItem else {
            logger.debug("No item selected for rename")
            return
        }

        if selected.itemType.canBeRenamed {
            renameState.startRename(itemId: selected.id, currentName: selected.name)
        }
    }

    func handleDeleteSelectedItem() {
        guard let selected = selectedItem else {
            logger.debug("No item selected for delete")
            return
        }

        if selected.itemType.canBeDeleted {
            deleteState.showDeleteConfirmation(for: selected)
        }
    }

    func performDelete(_ item: SidebarItem) async {
        logger.info("performDelete called for: \(item.name) (id: \(item.id))")

        // Find the next item to select before deletion
        let nextItemId = findNextItemAfterDelete(item)

        // For documents, use documentStore to ensure UI refresh
        if case .document(let document) = item.itemType {
            do {
                try await documentStore.deleteDocument(document)
                logger.info("Deleted document \(document.id)")

                // Select the next item
                await MainActor.run {
                    selectedItemId = nextItemId
                }

                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                logger.error("Failed to delete document: \(error.localizedDescription)")
                deleteState.showError(message: error.localizedDescription)
            }
        } else {
            // For non-document items (searches, chats, workflows)
            // Extract the actual ID from the prefixed ID format (e.g., "search:123" -> "123")
            let actualId: String
            if item.id.contains(":") {
                actualId = String(item.id.split(separator: ":")[1])
            } else {
                actualId = item.id
            }

            do {
                // Use the correct service based on item type
                switch item.itemType {
                case .savedSearch:
                    try await savedSearchService.deleteSavedSearch(actualId)
                    logger.info("Deleted saved search \(actualId)")
                case .conversation:
                    try await conversationService.deleteConversation(actualId)
                    logger.info("Deleted conversation \(actualId)")
                case .workflow:
                    try await workflowStore.deleteWorkflow(actualId)
                    logger.info("Deleted workflow \(actualId)")
                default:
                    logger.warning("Unknown item type for deletion")
                }

                // Select the next item
                await MainActor.run {
                    selectedItemId = nextItemId
                }

                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                logger.error("Failed to delete item: \(error.localizedDescription)")
                deleteState.showError(message: error.localizedDescription)
            }
        }
    }

    /// Find the next item to select after deleting the given item
    func findNextItemAfterDelete(_ itemToDelete: SidebarItem) -> String? {
        // Get all items in a flat list
        let allItems = cachedLibraryItems + cachedSearchItems + cachedChatItems + cachedWorkflowItems

        // Flatten the tree to find the item's position
        var flatList: [SidebarItem] = []
        func flatten(_ items: [SidebarItem]) {
            for item in items {
                flatList.append(item)
                if let children = item.children {
                    flatten(children)
                }
            }
        }
        flatten(allItems)

        // Find the index of the item to delete
        guard let index = flatList.firstIndex(where: { $0.id == itemToDelete.id }) else {
            return nil
        }

        // Try to select the next item, or previous if last
        if index + 1 < flatList.count {
            return flatList[index + 1].id
        } else if index > 0 {
            return flatList[index - 1].id
        } else {
            return nil
        }
    }

    /// Handles dropping documents onto the "New Chat" button.
    /// Creates a new chat with the dropped documents as context.
    func handleChatButtonDrop(itemIDs: [String]) -> Bool {
        let documentIds = itemIDs.map { itemID in
            // Extract actual ID (strip prefix like "doc:")
            if itemID.contains(":") {
                return String(itemID.split(separator: ":")[1])
            }
            return itemID
        }
        createNewChatWithDocuments(documentIds)
        return true
    }

    /// Creates a new chat conversation with the specified documents.
    /// Calls the onCreateChatWithDocuments callback to pass document IDs to ContentView.
    func createNewChatWithDocuments(_ documentIds: [String]) {
        logger.info("Creating new chat with \(documentIds.count) documents")
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }

    // MARK: - Section Header Drop Handlers

    /// Handles dropping items onto the Search section header.
    /// Switches to search view with dropped items as potential search scope.
    func handleSearchHeaderDrop(itemIDs: [String]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = itemIDs

        logger.info("Dropped \(documentIds.count) items on Search section")

        // Switch to search view with dropped items as context
        // In a full implementation, this would pass the document IDs to the search view
        // to use as the search scope
        viewMode = .search(nil)

        return true
    }

    func handleChatHeaderDrop(itemIDs: [String]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = itemIDs.map { itemID in
            if itemID.contains(":") {
                return String(itemID.split(separator: ":")[1])
            }
            return itemID
        }

        logger.info("Dropped \(documentIds.count) items on Chat section")

        // Switch to chat view with dropped items as context
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)

        return true
    }

    func handleWorkflowHeaderDrop(itemIDs: [String]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = itemIDs

        logger.info("Dropped \(documentIds.count) items on Workflow section")

        // Switch to workflow view with dropped items as inputs
        // In a full implementation, this would pass the document IDs to the workflow editor
        // to use as input nodes or variables
        viewMode = .workflow(nil)

        return true
    }

    func handleDropToRootLevel(itemIDs: [String]) -> Bool {
        logger.info("========== DROP TO ROOT STARTED ==========")
        logger.info("Moving \(itemIDs.count) items to root level (parent_id = nil)")

        Task {
            for itemID in itemIDs {
                logger.info("Moving item \(itemID) to root")
                await moveItemToRoot(itemId: itemID)
            }
            logger.info("========== DROP TO ROOT COMPLETED ==========")
        }

        return true
    }

    private func moveItemToRoot(itemId: String) async {
        logger.info("moveItemToRoot: \(itemId)")
        logger.info("START: \(itemId)")

        let actualItemId = extractActualId(from: itemId)

        do {
            // Move to root by setting parent to nil
            logger.info("Calling documentStore.moveDocument")
            let movedDoc = try await documentStore.moveDocument(actualItemId, toParent: nil)
            logger.info("moveDocument returned: \(movedDoc.name), parent: \(movedDoc.parentId ?? "nil")")

            logger.info("Move to root successful - rebuilding caches")
            logger.info("About to rebuild caches")

            // Explicitly rebuild caches to ensure UI updates
            await MainActor.run {
                logger.info("Inside MainActor.run, calling rebuildCaches()")
                rebuildCaches()
                logger.info("rebuildCaches() completed")

                let rootItems = cachedLibraryItems.filter { item in
                    if case .document(let doc) = item.itemType {
                        return doc.parentId == nil
                    }
                    return false
                }
                logger.info("Root-level items: \(rootItems.map { $0.name })")
            }
            logger.info("END - all done")

        } catch {
            logger.error("ERROR: \(error.localizedDescription)")
            logger.error("Move to root failed: \(error.localizedDescription)")
        }
    }

    private func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }
}

// MARK: - Library Row (for Open Libraries section)

/// Row displaying a single library in the Open Libraries section
/// Simple single-line style matching the rest of the sidebar
struct LibraryRow: View {
    let library: LibraryManager.LibraryReference
    let isCurrentLibrary: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            Label(library.displayName, systemImage: "book.closed")
        }
        .buttonStyle(.plain)
        .foregroundColor(isCurrentLibrary ? .accentColor : .primary)
    }
}
