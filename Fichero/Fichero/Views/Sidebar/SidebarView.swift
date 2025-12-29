// swiftlint:disable file_length
import SwiftUI
import UniformTypeIdentifiers

// swiftlint:disable:next type_body_length
/// Sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    @Binding var viewMode: AppViewMode
    @Binding var selectedItemId: String?

    // Observable stores - automatically trigger UI updates when @Published properties change
    @ObservedObject var documentStore: DocumentStore
    @ObservedObject var savedSearchService: SavedSearchService
    @ObservedObject var conversationService: ConversationService
    @ObservedObject var workflowStore: WorkflowStore

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Cache for sidebar items - rebuilt only when source data changes
    @State private var cachedLibraryItems: [SidebarItem] = []
    @State private var cachedSearchItems: [SidebarItem] = []
    @State private var cachedChatItems: [SidebarItem] = []
    @State private var cachedWorkflowItems: [SidebarItem] = []

    /// All cached items combined (for circular reference checks)
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
            .modifier(SidebarStyleModifiers())
            .modifier(SidebarToolbarModifiers(
                selectedItem: selectedItem,
                handleCreateNewFolder: handleCreateNewFolder,
                importFiles: importFiles,
                handleRenameSelectedItem: handleRenameSelectedItem,
                handleDeleteSelectedItem: handleDeleteSelectedItem
            ))
            .modifier(SidebarCacheModifiers(
                rebuildCaches: rebuildCaches,
                documentStore: documentStore,
                savedSearchService: savedSearchService,
                conversationService: conversationService,
                workflowStore: workflowStore,
                selectedItem: selectedItem,
                handleSelection: handleSelection
            ))
            .modifier(SidebarFocusedValueModifiers(
                selectedItem: selectedItem,
                handleCreateNewFolder: handleCreateNewFolder,
                handleRenameSelectedItem: handleRenameSelectedItem,
                handleDeleteSelectedItem: handleDeleteSelectedItem
            ))
            .modifier(SidebarDeleteAlertModifiers(
                deleteState: deleteState,
                performDelete: performDelete
            ))
    }

    // MARK: - Sidebar Content

    @ViewBuilder
    private var sidebarContent: some View {
        List(selection: $selectedItemId) {
            librarySectionView
            searchesSectionView
            chatSectionView
            workflowsSectionView
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
                    deleteState: deleteState,
                    documentStore: documentStore,
                    savedSearchService: savedSearchService,
                    conversationService: conversationService,
                    workflowStore: workflowStore
                )
                .padding(.leading, 4)
                .tag(item.id)
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
            }
            .onMove(perform: { _, _ in
                // Handle reordering of library items
                // This would require updating the backend collection order
            })
        } header: {
            SectionHeader(
                title: "Library",
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
                    deleteState: deleteState,
                    documentStore: documentStore,
                    savedSearchService: savedSearchService,
                    conversationService: conversationService,
                    workflowStore: workflowStore
                )
                .padding(.leading, 4)
                .tag(item.id)
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
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
            SectionHeader(title: "Searches", icon: "magnifyingglass")
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
                    deleteState: deleteState,
                    documentStore: documentStore,
                    savedSearchService: savedSearchService,
                    conversationService: conversationService,
                    workflowStore: workflowStore
                )
                .padding(.leading, 4)
                .tag(item.id)
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
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
            SectionHeader(title: "Chat", icon: "bubble.left.and.bubble.right")
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
                    deleteState: deleteState,
                    documentStore: documentStore,
                    savedSearchService: savedSearchService,
                    conversationService: conversationService,
                    workflowStore: workflowStore
                )
                .padding(.leading, 4)
                .tag(item.id)
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
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
            SectionHeader(title: "Workflows", icon: "arrow.triangle.branch")
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

    private func createNewSearch() {
        viewMode = .search(nil)
    }

    private func createNewChat() {
        viewMode = .chat(nil)
    }

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
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.image, .pdf, .plainText, .data]

        if panel.runModal() == .OK {
            // Get parent ID from selected item
            var parentId: String?
            if let selected = selectedItem, case .document(let doc) = selected.itemType {
                parentId = doc.id
            }

            // Import files
            Task {
                for url in panel.urls {
                    do {
                        _ = try await documentStore.importFile(at: url, parentId: parentId)
                        NSLog("[SidebarView] Imported: \(url.lastPathComponent)")
                    } catch {
                        NSLog("[SidebarView] Failed to import \(url.lastPathComponent): \(error)")
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
                NSLog("[SidebarView] Created new folder with parent: \(parentId ?? "root")")
            } catch {
                NSLog("[SidebarView] Failed to create folder: \(error)")
            }
        }
    }

    func handleRenameSelectedItem() {
        guard let selected = selectedItem else {
            NSLog("[SidebarView] No item selected for rename")
            return
        }

        if selected.itemType.canBeRenamed {
            renameState.startRename(itemId: selected.id, currentName: selected.name)
        }
    }

    func handleDeleteSelectedItem() {
        guard let selected = selectedItem else {
            NSLog("[SidebarView] No item selected for delete")
            return
        }

        if selected.itemType.canBeDeleted {
            deleteState.showDeleteConfirmation(for: selected)
        }
    }

    func performDelete(_ item: SidebarItem) async {
        NSLog("[SidebarView] performDelete called for: \(item.name) (id: \(item.id))")

        // Find the next item to select before deletion
        let nextItemId = findNextItemAfterDelete(item)

        // For documents, use documentStore to ensure UI refresh
        if case .document(let document) = item.itemType {
            do {
                try await documentStore.deleteDocument(document)
                NSLog("[SidebarView] Deleted document \(document.id)")

                // Select the next item
                await MainActor.run {
                    selectedItemId = nextItemId
                }

                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarView] Failed to delete document: \(error.localizedDescription)")
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
                    NSLog("[SidebarView] Deleted saved search \(actualId)")
                case .conversation:
                    try await conversationService.deleteConversation(actualId)
                    NSLog("[SidebarView] Deleted conversation \(actualId)")
                case .workflow:
                    try await workflowStore.deleteWorkflow(actualId)
                    NSLog("[SidebarView] Deleted workflow \(actualId)")
                default:
                    NSLog("[SidebarView] ⚠️ Unknown item type for deletion")
                }

                // Select the next item
                await MainActor.run {
                    selectedItemId = nextItemId
                }

                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarView] Failed to delete item: \(error.localizedDescription)")
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

    func createNewChatWithDocuments(_ documentIds: [String]) {
        NSLog("[SidebarView] Creating new chat with %d documents", documentIds.count)
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }

    // MARK: - Section Header Drop Handlers

    func handleSearchHeaderDrop(itemIDs: [String]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = itemIDs

        NSLog("[SidebarView] Dropped %d items on Search section", documentIds.count)

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

        NSLog("[SidebarView] Dropped %d items on Chat section", documentIds.count)

        // Switch to chat view with dropped items as context
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)

        return true
    }

    func handleWorkflowHeaderDrop(itemIDs: [String]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = itemIDs

        NSLog("[SidebarView] Dropped %d items on Workflow section", documentIds.count)

        // Switch to workflow view with dropped items as inputs
        // In a full implementation, this would pass the document IDs to the workflow editor
        // to use as input nodes or variables
        viewMode = .workflow(nil)

        return true
    }

    func handleDropToRootLevel(itemIDs: [String]) -> Bool {
        NSLog("[SidebarView] ========== DROP TO ROOT STARTED ==========")
        NSLog("[SidebarView] Moving \(itemIDs.count) items to root level (parent_id = nil)")

        Task {
            for itemID in itemIDs {
                NSLog("[SidebarView] Moving item \(itemID) to root")
                await moveItemToRoot(itemId: itemID)
            }
            NSLog("[SidebarView] ========== DROP TO ROOT COMPLETED ==========")
        }

        return true
    }

    private func moveItemToRoot(itemId: String) async {
        NSLog("[SidebarView] moveItemToRoot: \(itemId)")

        let actualItemId = extractActualId(from: itemId)

        do {
            // Move to root by setting parent to nil
            _ = try await documentStore.moveDocument(actualItemId, toParent: nil)
            NSLog("[SidebarView] ✅ Move to root successful - UI updates automatically via @Published")

        } catch {
            NSLog("[SidebarView] ❌ Move to root failed: \(error.localizedDescription)")
        }
    }

    private func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }
}

// MARK: - Section Header
struct SectionHeader: View {
    let title: String
    let icon: String
    let onDrop: (([String]) -> Bool)?

    @State private var isDropTargeted = false

    init(title: String, icon: String, onDrop: (([String]) -> Bool)? = nil) {
        self.title = title
        self.icon = icon
        self.onDrop = onDrop
    }

    var body: some View {
        Label(title, systemImage: icon)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isDropTargeted ? Color.accentColor.opacity(0.3) : Color.clear)
            )
            .dropDestination(for: String.self) { droppedIDs, _ in
                onDrop?(droppedIDs) ?? false
            } isTargeted: { isTargeted in
                isDropTargeted = isTargeted
            }
    }
}

// MARK: - Sidebar Item Row
struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @ObservedObject fileprivate var renameState: RenameStateManager
    @ObservedObject fileprivate var deleteState: DeleteStateManager
    @ObservedObject var documentStore: DocumentStore
    @ObservedObject var savedSearchService: SavedSearchService
    @ObservedObject var conversationService: ConversationService
    @ObservedObject var workflowStore: WorkflowStore

    @State private var isDropTargeted = false
    @FocusState private var isRenameFocused: Bool
    @State private var isCommittingRename = false

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    var body: some View {
        // Check if this is a folder type
        let isFolder: Bool = {
            if case .document(let doc) = item.itemType {
                return doc.docType == .folder
            }
            return false
        }()

        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                ForEach(children) { child in
                    SidebarItemRow(
                        item: child,
                        allCachedItems: allCachedItems,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore,
                        savedSearchService: savedSearchService,
                        conversationService: conversationService,
                        workflowStore: workflowStore
                    )
                    .tag(child.id)
                    .contextMenu {
                        SidebarItemContextMenu(
                            item: child,
                            renameState: renameState,
                            deleteState: deleteState,
                            documentStore: documentStore
                        )
                    }
                }
            } label: {
                itemLabel
                    .listRowBackground(isDropTargeted ? Color.accentColor : Color.clear)
                    .draggable(item.id)
                    .dropDestination(for: String.self) { droppedIDs, _ in
                        handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                    } isTargeted: { isTargeted in
                        isDropTargeted = isTargeted
                    }
            }
            .contextMenu {
                SidebarItemContextMenu(
                    item: item,
                    renameState: renameState,
                    deleteState: deleteState,
                    documentStore: documentStore
                )
            }
        } else if isFolder {
            // Empty folder - still needs to accept drops
            itemLabel
                .listRowBackground(
                    isDropTargeted ? Color.accentColor : Color.clear
                )
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropIntoFolder(
                        itemIDs: droppedIDs,
                        targetFolder: item
                    )
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
        } else {
            // Regular document - can be dragged and can accept drops to become siblings
            itemLabel
                .listRowBackground(
                    isDropTargeted ? Color.accentColor.opacity(0.3) : Color.clear
                )
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropBesideItem(itemIDs: droppedIDs, targetItem: item)
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                }
        }
    }

    private func handleDropBesideItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        NSLog("[SidebarView] ========== DROP BESIDE STARTED ==========")
        NSLog("[SidebarView] handleDropBesideItem called with \(itemIDs.count) items beside \(targetItem.name)")

        // Get the target item's parent (to make dropped items siblings of target)
        let targetParentId: String?
        if case .document(let targetDoc) = targetItem.itemType {
            targetParentId = targetDoc.parentId
            NSLog("[SidebarView] Target parent ID: \(targetParentId ?? "root")")
        } else {
            NSLog("[SidebarView] ⚠️ Target item is not a document, cannot determine parent")
            return false
        }

        // Move each dropped item to the same parent as the target
        for itemID in itemIDs {
            NSLog("[SidebarView] Moving item \(itemID) to be sibling of \(targetItem.name)")

            // Prevent dropping item onto itself
            guard itemID != targetItem.id else {
                NSLog("[SidebarView] ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            Task {
                if let parentId = targetParentId {
                    await moveItemToFolder(itemId: itemID, targetFolderId: parentId)
                } else {
                    // Move to root by setting parent to nil
                    let actualItemId = extractActualId(from: itemID)
                    do {
                        _ = try await documentStore.moveDocument(actualItemId, toParent: nil)
                        NSLog("[SidebarItemRow] ✅ Move to root successful")
                    } catch {
                        NSLog("[SidebarItemRow] ❌ Move to root failed: \(error.localizedDescription)")
                    }
                }
            }
        }

        NSLog("[SidebarView] ========== DROP BESIDE COMPLETED ==========")
        return true
    }

    private func handleDropIntoFolder(itemIDs: [String], targetFolder: SidebarItem) -> Bool {
        NSLog("[SidebarView] ========== DROP STARTED ==========")
        NSLog("[SidebarView] handleDropIntoFolder called with \(itemIDs.count) items onto \(targetFolder.name)")
        NSLog("[SidebarView] Item IDs: \(itemIDs)")
        NSLog("[SidebarView] Target folder ID: \(targetFolder.id)")
        NSLog("[SidebarView] Target folder itemType: \(targetFolder.itemType)")

        // Validate that target is actually a folder
        guard case .document(let targetDoc) = targetFolder.itemType,
              targetDoc.docType == .folder else {
            NSLog(
                "[SidebarView] ❌ Drop rejected: target \(targetFolder.name) " +
                "is not a folder (type: \(targetFolder.itemType))"
            )
            return false
        }

        NSLog("[SidebarView] ✅ Target \(targetFolder.name) is valid folder (docType: \(targetDoc.docType))")
        NSLog("[SidebarView] Target document ID from doc: \(targetDoc.id)")

        // Move each dropped item
        for itemID in itemIDs {
            NSLog("[SidebarView] Processing drop of item ID: \(itemID)")

            // Prevent dropping item onto itself
            guard itemID != targetFolder.id else {
                NSLog("[SidebarView] ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            // Validate circular reference: cannot drop folder into its own child
            if isDescendant(targetFolder.id, of: itemID) {
                NSLog("[SidebarView] ⚠️ Drop rejected: circular reference detected")
                continue
            }

            // Call backend to update parent
            NSLog("[SidebarView] ✅ Validation passed, calling moveItemToFolder")
            NSLog("[SidebarView]    Source ID: \(itemID)")
            NSLog("[SidebarView]    Target ID: \(targetFolder.id)")
            Task {
                await moveItemToFolder(itemId: itemID, targetFolderId: targetFolder.id)
            }
        }
        NSLog("[SidebarView] ========== DROP COMPLETED ==========")
        return true
    }

    private func handleDropOntoItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        // For non-folder items, we don't support dropping onto them
        NSLog("[SidebarView] Drop onto non-folder item not supported")
        return false
    }

    private func isDescendant(_ potentialDescendant: String, of ancestorId: String) -> Bool {
        // Check if potentialDescendant is a child/grandchild/etc of ancestorId
        // This prevents circular references (e.g., dragging a folder into its own child)

        // Find the ancestor item in cached items
        guard let ancestorItem = findItemById(ancestorId, in: allCachedItems) else {
            return false
        }

        // Recursively check if potentialDescendant is in ancestorItem's children tree
        return containsDescendant(potentialDescendant, in: ancestorItem)
    }

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

    private func containsDescendant(_ targetId: String, in item: SidebarItem) -> Bool {
        // Check if this item is the target
        if item.id == targetId {
            return true
        }

        // Recursively check children
        if let children = item.children {
            for child in children {
                if containsDescendant(targetId, in: child) {
                    return true
                }
            }
        }

        return false
    }

    private func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }

    private func moveItemToFolder(itemId: String, targetFolderId: String) async {
        NSLog("[SidebarView] moveItemToFolder: \(itemId) → \(targetFolderId)")

        // Extract actual IDs (strip prefix like "doc:")
        let actualItemId = extractActualId(from: itemId)
        let actualTargetId = extractActualId(from: targetFolderId)

        do {
            // Use documentStore (same pattern as rename/delete) - no refresh() needed!
            _ = try await documentStore.moveDocument(actualItemId, toParent: actualTargetId)
            NSLog("[SidebarView] ✅ Move successful - UI updates automatically via @Published")

        } catch {
            NSLog("[SidebarView] ❌ Move failed: \(error.localizedDescription)")
        }
    }

    private var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                let _ = NSLog("[SidebarItemRow.itemLabel] SHOWING TextField for: \(item.name) (id: \(item.id))")
                let _ = NSLog("[SidebarItemRow.itemLabel]   - renameState.renamingItemId: \(renameState.renamingItemId ?? "nil")")
                TextField("Name", text: $renameState.editingName)
                    .textFieldStyle(.plain)
                    .focused($isRenameFocused)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .onSubmit {
                        commitRename()
                    }
                    .onExitCommand {
                        renameState.cancelRename()
                        isRenameFocused = false
                    }
                    .onChange(of: isRenameFocused) { _, newValue in
                        if !newValue && renameState.renamingItemId == item.id && !isCommittingRename {
                            // Focus was lost without submitting, cancel rename
                            renameState.cancelRename()
                        }
                    }
                    .task {
                        // Automatically focus the TextField when rename starts
                        isRenameFocused = true
                    }
            } else {
                Text(item.name)
                    .lineLimit(1)
            }
        } icon: {
            Image(systemName: item.icon)
                .foregroundColor(iconColor)
        }
    }

    private func commitRename() {
        let newName = renameState.editingName.trimmingCharacters(in: .whitespacesAndNewlines)

        NSLog("[SidebarItemRow.commitRename] Committing rename for item: \(item.name) (id: \(item.id))")
        NSLog("[SidebarItemRow.commitRename]   - New name: \(newName)")
        NSLog("[SidebarItemRow.commitRename]   - renameState.renamingItemId: \(renameState.renamingItemId ?? "nil")")

        // Validate name
        guard !newName.isEmpty else {
            renameState.cancelRename()
            return
        }

        guard newName.count <= 255 else {
            renameState.cancelRename()
            return
        }

        // Mark that we're committing to prevent onChange from canceling
        isCommittingRename = true

        // Call backend to rename
        Task {
            await performRename(itemId: item.id, newName: newName)
            await MainActor.run {
                renameState.cancelRename()
                isCommittingRename = false
            }
        }
    }

    private func performRename(itemId: String, newName: String) async {
        NSLog("[SidebarItemRow.performRename] Called with itemId: \(itemId), newName: \(newName)")
        NSLog("[SidebarItemRow.performRename]   - Current row's item: \(item.name) (id: \(item.id))")
        NSLog("[SidebarItemRow.performRename]   - item.itemType: \(item.itemType)")

        // For document items, use DocumentStore which updates local state properly
        if case .document(let document) = item.itemType {
            NSLog("[SidebarItemRow.performRename]   - Renaming document: \(document.name) (id: \(document.id))")
            do {
                let updated = try await documentStore.renameDocument(document, to: newName)
                NSLog("[SidebarItemRow] Renamed document to '\(updated.name)'")
                // DocumentStore.renameDocument already updates @Published collections
                // SwiftUI will automatically rebuild the tree and maintain selection via ID
                // No manual restoration needed!
            } catch {
                NSLog("[SidebarItemRow] Failed to rename document: \(error.localizedDescription)")
            }
        } else {
            // For non-document items (searches, chats, workflows)
            let actualId: String
            if itemId.contains(":") {
                actualId = String(itemId.split(separator: ":")[1])
            } else {
                actualId = itemId
            }

            do {
                // Use the correct service based on item type
                switch item.itemType {
                case .savedSearch:
                    _ = try await savedSearchService.renameSavedSearch(actualId, newName: newName)
                    NSLog("[SidebarItemRow] Renamed saved search \(actualId) to '\(newName)'")
                case .conversation:
                    _ = try await conversationService.renameConversation(actualId, newTitle: newName)
                    NSLog("[SidebarItemRow] Renamed conversation \(actualId) to '\(newName)'")
                case .workflow:
                    _ = try await workflowStore.renameWorkflow(actualId, to: newName)
                    NSLog("[SidebarItemRow] Renamed workflow \(actualId) to '\(newName)'")
                default:
                    NSLog("[SidebarItemRow] ⚠️ Unknown item type for rename")
                }
                // UI updates automatically via @Published collections
            } catch {
                NSLog("[SidebarItemRow] Failed to rename item: \(error.localizedDescription)")
            }
        }
    }

    private var iconColor: Color {
        switch item.section {
        case .library:
            return .accentColor
        case .searches:
            return .orange
        case .chat:
            return .green
        case .workflows:
            return .purple
        }
    }
}

// MARK: - Sidebar Item Context Menu
struct SidebarItemContextMenu: View {
    let item: SidebarItem
    @ObservedObject fileprivate var renameState: RenameStateManager
    @ObservedObject fileprivate var deleteState: DeleteStateManager
    @ObservedObject var documentStore: DocumentStore

    var body: some View {
        Group {
            Button(action: { renameItem(item) }, label: {
                Label("Rename", systemImage: "pencil")
            })
            .disabled(!item.itemType.canBeRenamed)

            Divider()

            Button(action: { deleteItem(item) }, label: {
                Label("Delete", systemImage: "trash")
                    .foregroundColor(.red)
            })
            .keyboardShortcut(.delete, modifiers: .command)
            .disabled(!item.itemType.canBeDeleted)
        }
    }

    private func renameItem(_ item: SidebarItem) {
        NSLog("[SidebarItemContextMenu] renameItem called for: \(item.name) (id: \(item.id))")
        renameState.startRename(itemId: item.id, currentName: item.name)
        NSLog("[SidebarItemContextMenu]   - Set renameState.renamingItemId to: \(item.id)")
    }

    private func deleteItem(_ item: SidebarItem) {
        NSLog("[SidebarItemContextMenu] deleteItem called for: \(item.name) (id: \(item.id))")
        deleteState.showDeleteConfirmation(for: item)
        NSLog("[SidebarItemContextMenu]   - Set deleteState.itemToDelete to: \(item.name)")
    }
}

// MARK: - Preview

#Preview {
    SidebarView(
        viewMode: .constant(AppViewMode.library(nil)),
        selectedItemId: .constant(nil),
        documentStore: DocumentStore.preview,
        savedSearchService: SavedSearchService(),
        conversationService: ConversationService(),
        workflowStore: WorkflowStore()
    )
    .frame(width: 250, height: 500)
}

// MARK: - Extensions to add capability checks to ItemType

extension SidebarItem.ItemType {
    var canBeRenamed: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow:
            return true
        case .sectionHeader:
            return false
        }
    }

    var canBeDeleted: Bool {
        switch self {
        case .document, .savedSearch, .conversation, .workflow:
            return true
        case .sectionHeader:
            return false
        }
    }
}

// MARK: - State Managers

// swiftlint:disable:next private_over_fileprivate
fileprivate class RenameStateManager: ObservableObject {
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

// swiftlint:disable:next private_over_fileprivate
fileprivate class DeleteStateManager: ObservableObject {
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
        itemToDelete = nil
        deleteErrorMessage = ""
    }

    func showError(message: String) {
        deleteErrorMessage = message
        showingDeleteError = true
        showingDeleteConfirmation = false
    }
}

// MARK: - View Modifiers

private struct SidebarStyleModifiers: ViewModifier {
    func body(content: Content) -> some View {
        content
            .listStyle(.sidebar)
            .frame(minWidth: 200)
    }
}

private struct SidebarToolbarModifiers: ViewModifier {
    let selectedItem: SidebarItem?
    let handleCreateNewFolder: () -> Void
    let importFiles: () -> Void
    let handleRenameSelectedItem: () -> Void
    let handleDeleteSelectedItem: () -> Void

    func body(content: Content) -> some View {
        content
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    Button(action: handleCreateNewFolder) {
                        Image(systemName: "folder.badge.plus")
                    }
                    .help("New Folder")

                    Button(action: importFiles) {
                        Image(systemName: "square.and.arrow.down")
                    }
                    .help("Import Files")

                    Button(action: handleRenameSelectedItem) {
                        Image(systemName: "pencil")
                    }
                    .help("Rename")
                    .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeRenamed ?? false))

                    Button(action: handleDeleteSelectedItem) {
                        Image(systemName: "trash")
                    }
                    .help("Delete")
                    .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeDeleted ?? false))
                }
            }
    }
}

private struct SidebarCacheModifiers: ViewModifier {
    let rebuildCaches: () -> Void
    @ObservedObject var documentStore: DocumentStore
    @ObservedObject var savedSearchService: SavedSearchService
    @ObservedObject var conversationService: ConversationService
    @ObservedObject var workflowStore: WorkflowStore
    let selectedItem: SidebarItem?
    let handleSelection: (SidebarItem?) -> Void

    func body(content: Content) -> some View {
        content
            .task {
                // Build initial caches when view appears
                rebuildCaches()
            }
            .onChange(of: documentStore.collections) { _, _ in
                rebuildCaches()
            }
            .onChange(of: savedSearchService.savedSearches) { _, _ in
                rebuildCaches()
            }
            .onChange(of: conversationService.conversations) { _, _ in
                rebuildCaches()
            }
            .onChange(of: workflowStore.workflows) { _, _ in
                rebuildCaches()
            }
            .onChange(of: selectedItem) { _, newItem in
                handleSelection(newItem)
            }
    }
}

private struct SidebarFocusedValueModifiers: ViewModifier {
    let selectedItem: SidebarItem?
    let handleCreateNewFolder: () -> Void
    let handleRenameSelectedItem: () -> Void
    let handleDeleteSelectedItem: () -> Void

    func body(content: Content) -> some View {
        content
            .focusedValue(\.sidebarActions, SidebarActions(
                createFolder: handleCreateNewFolder,
                renameItem: handleRenameSelectedItem,
                deleteItem: handleDeleteSelectedItem
            ))
            .focusedValue(\.sidebarSelectionInfo, SidebarSelectionInfo(
                selectedItem: selectedItem,
                canRename: selectedItem?.itemType.canBeRenamed ?? false,
                canDelete: selectedItem?.itemType.canBeDeleted ?? false
            ))
    }
}

private struct SidebarDeleteAlertModifiers: ViewModifier {
    @ObservedObject var deleteState: DeleteStateManager
    let performDelete: (SidebarItem) async -> Void

    func body(content: Content) -> some View {
        content
            .alert(
                "Delete \"\(deleteState.itemToDelete?.name ?? "")\"?",
                isPresented: $deleteState.showingDeleteConfirmation,
                presenting: deleteState.itemToDelete,
                actions: { itemToDelete in
                    Button("Delete", role: .destructive) {
                        Task {
                            await performDelete(itemToDelete)
                        }
                    }
                    .keyboardShortcut(.defaultAction)
                    Button("Cancel", role: .cancel) {
                        deleteState.cancelDelete()
                    }
                },
                message: { _ in
                    Text("This action cannot be undone.")
                }
            )
            .alert("Delete Failed", isPresented: $deleteState.showingDeleteError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(deleteState.deleteErrorMessage)
            }
    }
}
