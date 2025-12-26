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

    // Expansion state
    @State private var expandedItems: Set<String> = []
    @State private var libraryExpanded = true
    @State private var searchesExpanded = true
    @State private var chatExpanded = true
    @State private var workflowsExpanded = true
    @State private var isChatDropTargeted = false

    var body: some View {
        List(selection: $selectedItem) {
            // LIBRARY section
            Section(isExpanded: $libraryExpanded) {
                ForEach(libraryItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item)
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
                        expandedItems: $expandedItems
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item)
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
                        expandedItems: $expandedItems
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item)
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
                        expandedItems: $expandedItems
                    )
                    .tag(item)
                    .contextMenu {
                        SidebarItemContextMenu(item: item)
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
                    SidebarItemRow(item: child, expandedItems: $expandedItems)
                        .tag(child)
                        .draggable(SidebarItemDragData(itemID: child.id))
                        .contextMenu {
                            SidebarItemContextMenu(item: child)
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
                    SidebarItemContextMenu(item: item)
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
            Text(item.name)
                .lineLimit(1)
        } icon: {
            Image(systemName: item.icon)
                .foregroundColor(iconColor)
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
    // Context menu actions would be handled by the parent view
    // Using action closures or by calling environment objects from the parent view

    var body: some View {
        Group {
            Button(action: { renameItem(item) }, label: {
                Label("Rename", systemImage: "pencil")
            })
            .disabled(!item.itemType.canBeRenamed)

            Divider()

            Button(action: { moveItemToFolder(item) }, label: {
                Label("Move to Folder", systemImage: "folder.badge.plus")
            })
            .disabled(!item.itemType.canBeMoved)

            Button(action: { duplicateItem(item) }, label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            })
            .disabled(!item.itemType.canBeDuplicated)

            Divider()

            Button(action: { deleteItem(item) }, label: {
                Label("Delete", systemImage: "trash")
                    .foregroundColor(.red)
            })
            .disabled(!item.itemType.canBeDeleted)
        }
    }

    private func renameItem(_ item: SidebarItem) {
        // This would trigger the rename functionality
        NSLog("[SidebarItemContextMenu] Rename item: \(item.name)")
        // In a real implementation, this would communicate back to the parent view
    }

    private func moveItemToFolder(_ item: SidebarItem) {
        // This would move the item to a folder
        NSLog("[SidebarItemContextMenu] Move item to folder: \(item.name)")
    }

    private func duplicateItem(_ item: SidebarItem) {
        // This would duplicate the item
        NSLog("[SidebarItemContextMenu] Duplicate item: \(item.name)")
    }

    private func deleteItem(_ item: SidebarItem) {
        // This would delete the item
        NSLog("[SidebarItemContextMenu] Delete item: \(item.name)")
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

    var canBeMoved: Bool {
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
