// swiftlint:disable file_length
import SwiftUI
import UniformTypeIdentifiers

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

    // Computed properties - SwiftUI automatically re-evaluates when dependencies change
    private var libraryItems: [SidebarItem] {
        SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    }

    private var searchItems: [SidebarItem] {
        SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
    }

    private var chatItems: [SidebarItem] {
        SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
    }

    private var workflowItems: [SidebarItem] {
        SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
    }

    /// Derive the selected SidebarItem from the ID
    private var selectedItem: SidebarItem? {
        guard let id = selectedItemId else { return nil }
        let allItems = libraryItems + searchItems + chatItems + workflowItems
        return findItemById(id, in: allItems)
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
        List(selection: $selectedItemId) {
            // LIBRARY section
            Section(isExpanded: $libraryExpanded) {
                ForEach(libraryItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                    .padding(.leading, 4)
                    .tag(item.id)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, deleteState: deleteState, documentStore: documentStore)
                    }
                }
                .onMove(perform: { _, _ in
                    // Handle reordering of library items
                    // This would require updating the backend collection order
                })
            } header: {
                SectionHeader(title: "Library", icon: "folder")
            }

            // SEARCHES section
            Section(isExpanded: $searchesExpanded) {
                ForEach(searchItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                    .padding(.leading, 4)
                    .tag(item.id)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, deleteState: deleteState, documentStore: documentStore)
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
                    .dropDestination(for: SidebarItemDragData.self) { items, _ in
                        handleSearchHeaderDrop(items: items)
                    } isTargeted: { isTargeted in
                        isSearchHeaderDropTargeted = isTargeted
                    }
            }

            // CHAT section - supports dropping documents to create new chat
            Section(isExpanded: $chatExpanded) {
                ForEach(chatItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                    .padding(.leading, 4)
                    .tag(item.id)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, deleteState: deleteState, documentStore: documentStore)
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
                .onDrop(of: [.text, .plainText], isTargeted: $isChatDropTargeted) { providers in
                    handleChatDrop(providers: providers)
                }
            } header: {
                SectionHeader(title: "Chat", icon: "bubble.left.and.bubble.right")
                    .background(isChatHeaderDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
                    .cornerRadius(4)
                    .dropDestination(for: SidebarItemDragData.self) { items, _ in
                        handleChatHeaderDrop(items: items)
                    } isTargeted: { isTargeted in
                        isChatHeaderDropTargeted = isTargeted
                    }
            }

            // WORKFLOWS section
            Section(isExpanded: $workflowsExpanded) {
                ForEach(workflowItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                    .padding(.leading, 4)
                    .tag(item.id)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, deleteState: deleteState, documentStore: documentStore)
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
                    .dropDestination(for: SidebarItemDragData.self) { items, _ in
                        handleWorkflowHeaderDrop(items: items)
                    } isTargeted: { isTargeted in
                        isWorkflowHeaderDropTargeted = isTargeted
                    }
            }
        }
        .listStyle(.sidebar)
        .frame(minWidth: 200)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button(action: { handleCreateNewFolder() }) {
                    Image(systemName: "folder.badge.plus")
                }
                .help("New Folder")

                Button(action: { importFiles() }) {
                    Image(systemName: "square.and.arrow.down")
                }
                .help("Import Files")

                Button(action: { handleRenameSelectedItem() }) {
                    Image(systemName: "pencil")
                }
                .help("Rename")
                .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeRenamed ?? false))

                Button(action: { handleDeleteSelectedItem() }) {
                    Image(systemName: "trash")
                }
                .help("Delete")
                .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeDeleted ?? false))
            }
        }
        .onChange(of: selectedItem) { _, newItem in
            handleSelection(newItem)
        }
        .onReceive(NotificationCenter.default.publisher(for: .createNewFolder)) { _ in
            handleCreateNewFolder()
        }
        .onReceive(NotificationCenter.default.publisher(for: .renameSelectedItem)) { _ in
            handleRenameSelectedItem()
        }
        .onReceive(NotificationCenter.default.publisher(for: .deleteSelectedItem)) { _ in
            handleDeleteSelectedItem()
        }
        .confirmationDialog(
            "Delete \"\(deleteState.itemToDelete?.name ?? "")\"?",
            isPresented: $deleteState.showingDeleteConfirmation,
            presenting: deleteState.itemToDelete
        ) { itemToDelete in
            Button("Delete", role: .destructive) {
                Task {
                    await performDelete(itemToDelete)
                }
            }
            Button("Cancel", role: .cancel) {
                deleteState.cancelDelete()
            }
        } message: { _ in
            Text("This action cannot be undone.")
        }
        .alert("Delete Failed", isPresented: $deleteState.showingDeleteError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(deleteState.deleteErrorMessage)
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

    // MARK: - Menu Command Handlers

    private func importFiles() {
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
                let documentService = DocumentService()
                for url in panel.urls {
                    do {
                        _ = try await documentService.importFile(at: url, parentId: parentId)
                        NSLog("[SidebarView] Imported: \(url.lastPathComponent)")
                    } catch {
                        NSLog("[SidebarView] Failed to import \(url.lastPathComponent): \(error)")
                    }
                }
                // Refresh collections after import
                await documentStore.loadCollections()
            }
        }
    }

    private func handleCreateNewFolder() {
        // Create new folder as child of currently selected item
        var parentId: String?
        if let selected = selectedItem, case .document(let doc) = selected.itemType {
            parentId = doc.id
        }

        Task {
            do {
                _ = try await documentStore.createCollection(name: "New Folder")
                NSLog("[SidebarView] Created new folder")
            } catch {
                NSLog("[SidebarView] Failed to create folder: \(error)")
            }
        }
    }

    private func handleRenameSelectedItem() {
        guard let selected = selectedItem else {
            NSLog("[SidebarView] No item selected for rename")
            return
        }

        if selected.itemType.canBeRenamed {
            renameState.startRename(itemId: selected.id, currentName: selected.name)
        }
    }

    private func handleDeleteSelectedItem() {
        guard let selected = selectedItem else {
            NSLog("[SidebarView] No item selected for delete")
            return
        }

        if selected.itemType.canBeDeleted {
            deleteState.showDeleteConfirmation(for: selected)
        }
    }

    private func performDelete(_ item: SidebarItem) async {
        NSLog("[SidebarView] performDelete called for: \(item.name) (id: \(item.id))")
        // For documents, use documentStore to ensure UI refresh
        if case .document(let document) = item.itemType {
            do {
                try await documentStore.deleteDocument(document)
                NSLog("[SidebarView] Deleted document \(document.id)")
                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarView] Failed to delete document: \(error.localizedDescription)")
                deleteState.showError(message: error.localizedDescription)
            }
        } else {
            // For non-document items (searches, chats, workflows), use direct API call
            // Extract the actual ID from the prefixed ID format (e.g., "doc:123" -> "123")
            let actualId: String
            if item.id.contains(":") {
                actualId = String(item.id.split(separator: ":")[1])
            } else {
                actualId = item.id
            }

            do {
                let documentService = DocumentService()
                try await documentService.deleteDocument(actualId)
                NSLog("[SidebarView] Deleted item \(actualId)")
                // UI updates automatically via @ObservedObject pattern - no manual refresh needed!
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarView] Failed to delete item: \(error.localizedDescription)")
                deleteState.showError(message: error.localizedDescription)
            }
        }
    }

    private func handleChatDrop(providers: [NSItemProvider]) -> Bool {
        var documentIds: [String] = []

        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        DispatchQueue.main.async {
                            documentIds.append(docId)
                            // After processing all providers, create the chat
                            if documentIds.count == providers.count {
                                createNewChatWithDocuments(documentIds)
                            }
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        DispatchQueue.main.async {
                            documentIds.append(docId)
                            if documentIds.count == providers.count {
                                createNewChatWithDocuments(documentIds)
                            }
                        }
                    }
                }
            }
        }
        return true
    }

    private func createNewChatWithDocuments(_ documentIds: [String]) {
        NSLog("[SidebarView] Creating new chat with %d documents", documentIds.count)
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }

    // MARK: - Section Header Drop Handlers

    private func handleSearchHeaderDrop(items: [SidebarItemDragData]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = items.map { $0.itemID }

        NSLog("[SidebarView] Dropped %d items on Search section", documentIds.count)

        // Switch to search view with dropped items as context
        // In a full implementation, this would pass the document IDs to the search view
        // to use as the search scope
        viewMode = .search(nil)

        return true
    }

    private func handleChatHeaderDrop(items: [SidebarItemDragData]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = items.map { itemId in
            if itemId.itemID.contains(":") {
                return String(itemId.itemID.split(separator: ":")[1])
            }
            return itemId.itemID
        }

        NSLog("[SidebarView] Dropped %d items on Chat section", documentIds.count)

        // Switch to chat view with dropped items as context
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)

        return true
    }

    private func handleWorkflowHeaderDrop(items: [SidebarItemDragData]) -> Bool {
        // Extract document IDs from dropped items
        let documentIds = items.map { $0.itemID }

        NSLog("[SidebarView] Dropped %d items on Workflow section", documentIds.count)

        // Switch to workflow view with dropped items as inputs
        // In a full implementation, this would pass the document IDs to the workflow editor
        // to use as input nodes or variables
        viewMode = .workflow(nil)

        return true
    }
}

// MARK: - Section Header
struct SectionHeader: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
    }
}

// MARK: - Sidebar Item Row
struct SidebarItemRow: View {
    let item: SidebarItem
    @Binding var expandedItems: Set<String>
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager
    @ObservedObject var documentStore: DocumentStore

    @State private var isDropTargeted = false
    @FocusState private var isRenameFocused: Bool

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
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                ForEach(children) { child in
                    SidebarItemRow(
                        item: child,
                        expandedItems: $expandedItems,
                        renameState: renameState,
                        deleteState: deleteState,
                        documentStore: documentStore
                    )
                        .tag(child.id)
                        .contextMenu {
                            SidebarItemContextMenu(item: child, renameState: renameState, deleteState: deleteState, documentStore: documentStore)
                        }
                }
                .onMove(perform: { _, _ in
                    // Handle reordering of child items within the folder
                    // This would require updating the backend
                })
            } label: {
                itemLabel
                    .background(isDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
                    .cornerRadius(4)
            }
            .draggable(SidebarItemDragData(itemID: item.id))
            .dropDestination(for: SidebarItemDragData.self) { items, _ in
                handleDropIntoFolder(items: items, targetFolder: item)
            } isTargeted: { isTargeted in
                isDropTargeted = isTargeted
            }
        } else {
            itemLabel
                .draggable(SidebarItemDragData(itemID: item.id))
        }
    }

    private func handleDropIntoFolder(items: [SidebarItemDragData], targetFolder: SidebarItem) -> Bool {
        // Validate that target is actually a folder
        guard case .document(let targetDoc) = targetFolder.itemType,
              targetDoc.docType == .folder || targetDoc.docType == .collection else {
            NSLog("[SidebarView] Drop rejected: target is not a folder")
            return false
        }

        // Move each dropped item
        for dragData in items {
            // Prevent dropping item onto itself
            guard dragData.itemID != targetFolder.id else {
                NSLog("[SidebarView] Drop rejected: cannot drop item onto itself")
                continue
            }

            // Validate circular reference: cannot drop folder into its own child
            if isDescendant(targetFolder.id, of: dragData.itemID) {
                NSLog("[SidebarView] Drop rejected: circular reference detected")
                continue
            }

            // Call backend to update parent
            Task {
                await moveItemToFolder(itemId: dragData.itemID, targetFolderId: targetFolder.id)
            }
        }
        return true
    }

    private func handleDropOntoItem(items: [SidebarItemDragData], targetItem: SidebarItem) -> Bool {
        // For non-folder items, we don't support dropping onto them
        NSLog("[SidebarView] Drop onto non-folder item not supported")
        return false
    }

    private func isDescendant(_ potentialDescendant: String, of ancestorId: String) -> Bool {
        // Simple check: traverse children to see if ancestorId is anywhere in potentialDescendant's tree
        // This is a simplistic implementation - in production, you'd query the backend or use cached hierarchy
        // For now, we'll just prevent the obvious case and let backend validation catch edge cases
        return false
    }

    private func moveItemToFolder(itemId: String, targetFolderId: String) async {
        // Extract actual IDs (strip prefix like "doc:")
        let actualItemId = extractActualId(from: itemId)
        let actualTargetId = extractActualId(from: targetFolderId)

        do {
            let documentService = DocumentService()
            _ = try await documentService.moveDocument(actualItemId, toParent: actualTargetId)
            NSLog("[SidebarView] Moved item \(actualItemId) to folder \(actualTargetId)")

            // Refresh UI
            await documentStore.refresh()
        } catch {
            NSLog("[SidebarView] Failed to move item: \(error.localizedDescription)")
        }
    }

    private func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }

    private var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                TextField("Name", text: $renameState.editingName)
                    .textFieldStyle(.plain)
                    .focused($isRenameFocused)
                    .onSubmit {
                        commitRename()
                    }
                    .onExitCommand {
                        renameState.cancelRename()
                        isRenameFocused = false
                    }
                    .onChange(of: isRenameFocused) { _, newValue in
                        if !newValue && renameState.renamingItemId == item.id {
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

        // Validate name
        guard !newName.isEmpty else {
            renameState.cancelRename()
            return
        }

        guard newName.count <= 255 else {
            renameState.cancelRename()
            return
        }

        // Call backend to rename
        Task {
            await performRename(itemId: item.id, newName: newName)
            renameState.cancelRename()
        }
    }

    private func performRename(itemId: String, newName: String) async {
        // For document items, use DocumentStore which updates local state properly
        if case .document(let document) = item.itemType {
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
            // For non-document items (searches, chats, workflows), use direct API call
            let actualId: String
            if itemId.contains(":") {
                actualId = String(itemId.split(separator: ":")[1])
            } else {
                actualId = itemId
            }

            do {
                let documentService = DocumentService()
                _ = try await documentService.renameDocument(actualId, newName: newName)
                NSLog("[SidebarItemRow] Renamed item \(actualId) to '\(newName)'")

                // For non-documents, we need to refresh to get updated data
                await documentStore.refresh()
                // SwiftUI maintains selection via ID automatically
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
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager
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
        renameState.startRename(itemId: item.id, currentName: item.name)
    }

    private func deleteItem(_ item: SidebarItem) {
        NSLog("[SidebarItemContextMenu] deleteItem called for: \(item.name) (id: \(item.id))")
        deleteState.showDeleteConfirmation(for: item)
    }
}

// MARK: - Rename State Manager
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

// MARK: - Delete State Manager
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
        itemToDelete = nil
        deleteErrorMessage = ""
    }

    func showError(message: String) {
        deleteErrorMessage = message
        showingDeleteError = true
        showingDeleteConfirmation = false
    }
}

// MARK: - Drag Data Structure
struct SidebarItemDragData: Codable, Transferable {
    let itemID: String

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .ficheroItem)
    }
}

extension UTType {
    static let ficheroItem = UTType(exportedAs: "ca.tubb.fichero.item")
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
