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
                }
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
                }

                // New Search button
                Button(action: { createNewSearch() }) {
                    Label("New Search...", systemImage: "plus")
                        .foregroundColor(.secondary)
                }
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
                }

                // New Chat button with drop support
                Button(action: { createNewChat() }) {
                    HStack {
                        Label("New Chat...", systemImage: "plus")
                            .foregroundColor(isChatDropTargeted ? .accentColor : .secondary)
                        if isChatDropTargeted {
                            Spacer()
                            Image(systemName: "arrow.down.circle.fill")
                                .foregroundColor(.accentColor)
                        }
                    }
                }
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
                }

                // New Workflow button
                Button(action: { createNewWorkflow() }) {
                    Label("New Workflow...", systemImage: "plus")
                        .foregroundColor(.secondary)
                }
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
                }
            } label: {
                itemLabel
            }
        } else {
            itemLabel
        }
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

// MARK: - Preview

#Preview {
    SidebarView(
        viewMode: .constant(.library(nil)),
        selectedItem: .constant(nil),
        libraryItems: [],
        searchItems: [],
        chatItems: [],
        workflowItems: []
    )
    .frame(width: 250, height: 500)
}
