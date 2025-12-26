// swiftlint:disable file_length
import SwiftUI
import UniformTypeIdentifiers

/// Sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?

    // Section data
    let libraryItems: [SidebarItem]
    let searchItems: [SidebarItem]
    let chatItems: [SidebarItem]
    let workflowItems: [SidebarItem]

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // Document store for CRUD operations
    var documentStore: DocumentStore?

    // Expansion state
    @State private var expandedItems: Set<String> = []
    @State private var libraryExpanded = true
    @State private var searchesExpanded = true
    @State private var chatExpanded = true
    @State private var workflowsExpanded = true
    @State private var isChatDropTargeted = false

    // Rename state
    @StateObject private var renameState = RenameStateManager()

    var body: some View {
        List(selection: $selectedItem) {
            // LIBRARY section
            Section(isExpanded: $libraryExpanded) {
                ForEach(libraryItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, documentStore: documentStore)
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
                        renameState: renameState
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, documentStore: documentStore)
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
            } header: {
                SectionHeader(title: "Searches", icon: "magnifyingglass")
            }

            // CHAT section - supports dropping documents to create new chat
            Section(isExpanded: $chatExpanded) {
                ForEach(chatItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, documentStore: documentStore)
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
                .onDrop(of: [.text, .plainText], isTargeted: $isChatDropTargeted) { providers in
                    handleChatDrop(providers: providers)
                }
            } header: {
                SectionHeader(title: "Chat", icon: "bubble.left.and.bubble.right")
            }

            // WORKFLOWS section
            Section(isExpanded: $workflowsExpanded) {
                ForEach(workflowItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        renameState: renameState
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item, renameState: renameState, documentStore: documentStore)
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
            } header: {
                SectionHeader(title: "Workflows", icon: "arrow.triangle.branch")
            }
        }
        .listStyle(.sidebar)
        .frame(minWidth: 200)
        .onChange(of: selectedItem) { _, newItem in
            handleSelection(newItem)
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
    var documentStore: DocumentStore?

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
                        documentStore: documentStore
                    )
                        .tag(child)
                        .draggable(SidebarItemDragData(itemID: child.id))
                        .contextMenu {
                            SidebarItemContextMenu(item: child, renameState: renameState, documentStore: documentStore)
                        }
                        .dropDestination(for: SidebarItemDragData.self) { items, _ in
                            // Handle dropping items into this folder
                            handleDropIntoFolder(items: items, targetFolder: child)
                            return true
                        }
                }
                .onMove(perform: { _, _ in
                    // Handle reordering of child items within the folder
                    // This would require updating the backend
                })
            } label: {
                itemLabel
                    .draggable(SidebarItemDragData(itemID: item.id))
                    .dropDestination(for: SidebarItemDragData.self) { items, _ in
                        // Handle dropping items into this folder
                        handleDropIntoFolder(items: items, targetFolder: item)
                        return true
                    }
            }
        } else {
            itemLabel
                .draggable(SidebarItemDragData(itemID: item.id))
                .dropDestination(for: SidebarItemDragData.self) { items, _ in
                    // Handle dropping items onto this item
                    handleDropOntoItem(items: items, targetItem: item)
                    return true
                }
                .contextMenu {
                    SidebarItemContextMenu(item: item, renameState: renameState, documentStore: documentStore)
                }
        }
    }

    private func handleDropIntoFolder(items: [SidebarItemDragData], targetFolder: SidebarItem) {
        // This would call backend to move items into the folder
        NSLog("[SidebarView] Dropping \(items.count) items into folder: \(targetFolder.name)")
    }

    private func handleDropOntoItem(items: [SidebarItemDragData], targetItem: SidebarItem) {
        // This would call backend to handle dropping items onto an item
        NSLog("[SidebarView] Dropping \(items.count) items onto item: \(targetItem.name)")
    }

    private var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                TextField("Name", text: $renameState.editingName, onCommit: {
                    commitRename()
                })
                .textFieldStyle(.plain)
                .onExitCommand {
                    renameState.cancelRename()
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
        // Extract the actual ID from the prefixed ID format (e.g., "doc:123" -> "123")
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
        } catch {
            NSLog("[SidebarItemRow] Failed to rename item: \(error.localizedDescription)")
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
    @StateObject private var deleteState = DeleteStateManager()
    var documentStore: DocumentStore?

    var body: some View {
        Group {
            Button(action: { renameItem(item) }, label: {
                Label("Rename", systemImage: "pencil")
            })
            .disabled(!item.itemType.canBeRenamed)

            Divider()

            Button(action: { duplicateItem(item) }, label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            })
            .disabled(!item.itemType.canBeDuplicated)

            Divider()

            Button(action: { deleteItem(item) }, label: {
                Label("Delete", systemImage: "trash")
                    .foregroundColor(.red)
            })
            .keyboardShortcut(.delete, modifiers: .command)
            .disabled(!item.itemType.canBeDeleted)
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

    private func renameItem(_ item: SidebarItem) {
        renameState.startRename(itemId: item.id, currentName: item.name)
    }

    private func duplicateItem(_ item: SidebarItem) {
        // This would duplicate the item
        NSLog("[SidebarItemContextMenu] Duplicate item: \(item.name)")
    }

    private func deleteItem(_ item: SidebarItem) {
        deleteState.showDeleteConfirmation(for: item)
    }

    private func performDelete(_ item: SidebarItem) async {
        // For documents, use documentStore to ensure UI refresh
        if case .document(let document) = item.itemType, let store = documentStore {
            do {
                try await store.deleteDocument(document)
                NSLog("[SidebarItemContextMenu] Deleted document \(document.id)")
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarItemContextMenu] Failed to delete document: \(error.localizedDescription)")
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
                NSLog("[SidebarItemContextMenu] Deleted item \(actualId)")
                deleteState.cancelDelete()
            } catch {
                NSLog("[SidebarItemContextMenu] Failed to delete item: \(error.localizedDescription)")
                deleteState.showError(message: error.localizedDescription)
            }
        }
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
struct SidebarItemDragData: Transferable {
    let itemID: String

    static var transferRepresentation: some TransferRepresentation {
        ProxyRepresentation {
            $0.itemID
        }
    }
}

// MARK: - Preview

#Preview {
    let emptyLibraryItems: [SidebarItem] = []
    let emptySearchItems: [SidebarItem] = []
    let emptyChatItems: [SidebarItem] = []
    let emptyWorkflowItems: [SidebarItem] = []

    SidebarView(
        viewMode: .constant(AppViewMode.library(nil)),
        selectedItem: .constant(nil),
        libraryItems: emptyLibraryItems,
        searchItems: emptySearchItems,
        chatItems: emptyChatItems,
        workflowItems: emptyWorkflowItems
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

    var canBeDuplicated: Bool {
        switch self {
        case .document:
            return true
        case .savedSearch, .conversation, .workflow, .sectionHeader:
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
