import SwiftUI
import UniformTypeIdentifiers
import AppKit
import Combine

/// Sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?

    // Environment objects - injected from parent
    @EnvironmentObject private var documentStore: DocumentStore
    @EnvironmentObject private var searchService: SavedSearchService
    @EnvironmentObject private var conversationService: ConversationService
    @EnvironmentObject private var workflowService: WorkflowService

    // Section data - injected from parent (computed in ContentView)
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
    
    // Rename state
    @State private var renamingItemId: String? = nil

    var body: some View {
        List(selection: $selectedItem) {
            // LIBRARY section
            Section(isExpanded: $libraryExpanded) {
                ForEach(libraryItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        viewMode: $viewMode,
                        selectedItem: $selectedItem
                    )
                    .tag(item)
                }
            } header: {
                SectionHeader(title: "Library", icon: "folder")
            }
            .onDrop(of: [.fileURL], isTargeted: $isChatDropTargeted) { providers -> Bool in
                handleLibrarySectionDrop(providers: providers)
            }

            // SEARCHES section
            Section(isExpanded: $searchesExpanded) {
                ForEach(searchItems) { item in
                    SidebarItemRow(
                        item: item,
                        expandedItems: $expandedItems,
                        viewMode: $viewMode,
                        selectedItem: $selectedItem
                    )
                    .tag(item)
                }

                // New Search button
                Button(
                    action: { createNewSearch() },
                    label: {
                        Label("New Search...", systemImage: "plus")
                            .foregroundColor(.secondary)
                    }
                )
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
                        viewMode: $viewMode,
                        selectedItem: $selectedItem
                    )
                    .tag(item)
                }

                // New Chat button with drop support
                Button(
                    action: { createNewChat() },
                    label: {
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
                )
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
                        viewMode: $viewMode,
                        selectedItem: $selectedItem
                    )
                    .tag(item)
                }

                // New Workflow button
                Button(
                    action: { createNewWorkflow() },
                    label: {
                        Label("New Workflow...", systemImage: "plus")
                            .foregroundColor(.secondary)
                    }
                )
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
        .onReceive(documentStore.documentChangePublisher.catch { error in
            Empty(completeImmediately: true)
        }.receive(on: DispatchQueue.main)) { change in
            handleDocumentChange(change)
        }
    }

    // MARK: - Actions

    /// Handle document change events from the publisher
    private func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated(_):
            // Update handled by parent view recomputing libraryItems
            break

        case .collectionSelected(let collection):
            // Update selection if the selected collection is in our library items
            if let item = libraryItems.first(where: { $0.id == collection.id }) {
                selectedItem = item
            }

        case .documentsUpdated(_):
            // Update handled by parent view
            break

        case .documentDeleted(_):
            // Remove deleted document from UI
            // Note: The parent view will recompute libraryItems, but we can also handle it here
            // for immediate feedback
            break

        case .documentCreated(_):
            // New document created - parent view will recompute libraryItems
            break
        }
    }

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
            // No action needed for section headers
            return
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

    /// Handle drop on Library section (create new collection with imported files)
    private func handleLibrarySectionDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false

        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { (urlData, error) in
                    DispatchQueue.main.async {
                        if let urlData = urlData as? Data,
                           let url = URL(dataRepresentation: urlData, relativeTo: nil) {
                            self.handleFileDropOnLibrary(url: url)
                            handled = true
                        }
                    }
                }
            }
        }

        return handled
    }

    /// Handle file dropped on Library section
    private func handleFileDropOnLibrary(url: URL) {
        NSLog("[Sidebar] File dropped on Library section: %@", url.path)

        Task {
            do {
                // Import file as a top-level document (no parent)
                let importedDoc = try await documentStore.importFile(at: url, parentId: nil)
                NSLog("[Sidebar] Successfully imported file to library: %@", importedDoc.name)
                
                // Show success alert
                if let window = NSApp.keyWindow {
                    let alert = NSAlert()
                    alert.messageText = "File Imported"
                    alert.informativeText = "\"\(importedDoc.name)\" was successfully imported to your library."
                    alert.addButton(withTitle: "OK")
                    alert.beginSheetModal(for: window, completionHandler: nil)
                }
            } catch {
                NSLog("[Sidebar] Error importing file to library: %@", String(describing: error))
                
                // Show error alert
                if let window = NSApp.keyWindow {
                    let alert = NSAlert()
                    alert.messageText = "Import Failed"
                    alert.informativeText = "Failed to import file: \(error.localizedDescription)"
                    alert.addButton(withTitle: "OK")
                    alert.beginSheetModal(for: window, completionHandler: nil)
                }
            }
        }
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
    @Binding var renamingItemId: String?
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var documentService: DocumentService
    @EnvironmentObject var searchService: SavedSearchService
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var workflowService: WorkflowService
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    // Drag and drop state
    @State private var isDragging = false
    @State private var isDropTargeted = false
    
    // Rename state
    @State private var renameError: String? = nil

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
                        viewMode: $viewMode,
                        selectedItem: $selectedItem
                    )
                    .tag(child)
                }
            } label: {
                itemLabel
            }
            .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers -> Bool in
                handleDrop(providers: providers)
            }
        } else {
            itemLabel
                .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers -> Bool in
                    handleDrop(providers: providers)
                }
        }
    }

    private var itemLabel: some View {
        HStack {
            if renamingItemId == item.id {
                // Show inline rename field
                InlineRenameField(
                    currentName: item.name,
                    placeholder: "Enter new name",
                    onCommit: { newName in
                        try await handleRename(newName: newName)
                        renamingItemId = nil
                    },
                    onCancel: {
                        renamingItemId = nil
                    }
                )
                .transition(.opacity.combined(with: .scale))
            } else {
                // Show normal label
                Label {
                    Text(item.name)
                        .lineLimit(1)
                } icon: {
                    Image(systemName: item.icon)
                        .foregroundColor(iconColor)
                }

                Spacer()

                // Show progress indicator if enabled and progress is available
                if item.showProgress, let progress = item.progress {
                    ProgressView(value: progress, total: 1.0)
                        .progressViewStyle(LinearProgressViewStyle())
                        .frame(width: 40)
                        .scaleEffect(CGSize(width: 0.7, height: 0.7))
                }
            }
        }
        .opacity(isDragging ? 0.5 : 1.0)
        .background(isDropTargeted ? Color.accentColor.opacity(0.1) : Color.clear)
        .cornerRadius(4)
        .onDrag {
            // Only allow dragging for documents and folders
            if case .document(let document) = item.itemType {
                // Create item provider with document ID
                let provider = NSItemProvider(object: document.id as NSString)
                return provider
            }
            return NSItemProvider()
        }
        .contextMenu {
            switch item.itemType {
            case .document(let document):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedDoc = try await documentService.duplicateDocument(document.id)
                            print("Document duplicated: \(duplicatedDoc.name)")
                            
                            // Show success alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Document Duplicated"
                                alert.informativeText = "\"\(duplicatedDoc.name)\" was successfully duplicated."
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        } catch {
                            print("Error duplicating document: \(error)")
                            
                            // Show error alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Error Duplicating Document"
                                alert.informativeText = "Failed to duplicate document: \(error.localizedDescription)"
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    // TODO: Implement new folder
                    print("Create new folder in documents")
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await documentService.deleteDocument(document.id)
                            print("Document deleted: \(document.name)")
                            
                            // Show success alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Document Deleted"
                                alert.informativeText = "\"\(document.name)\" was successfully deleted."
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }

                            // The reactive architecture will handle UI updates automatically
                        } catch {
                            print("Error deleting document: \(error)")
                            
                            // Show error alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Error Deleting Document"
                                alert.informativeText = "Failed to delete document: \(error.localizedDescription)"
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .savedSearch(let search):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedSearch = try await searchService.duplicateSavedSearch(search.id)
                            print("Saved search duplicated: \(duplicatedSearch.query)")
                        } catch {
                            print("Error duplicating saved search: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    // TODO: Implement new folder
                    print("Create new folder in searches")
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await searchService.deleteSavedSearch(search.id)
                            print("Saved search deleted: \(search.name)")
                        } catch {
                            print("Error deleting saved search: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .conversation(let conversation):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let result = try await conversationService.duplicateConversation(conversation.id)
                            print("Conversation duplicated: \(result.title)")
                        } catch {
                            print("Error duplicating conversation: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    // TODO: Implement new folder
                    print("Create new folder in chat")
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await conversationService.deleteConversation(conversation.id)
                            print("Conversation deleted: \(conversation.title)")
                        } catch {
                            print("Error deleting conversation: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .workflow(let workflow):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedWorkflow = try await workflowService.duplicateWorkflow(workflow.id)
                            print("Workflow duplicated: \(duplicatedWorkflow.name)")
                        } catch {
                            print("Error duplicating workflow: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("Import...") {
                    // Placeholder for import workflow
                    print("Import workflow")
                }

                Button("Export...") {
                    // Placeholder for export workflow
                    print("Export workflow: \(item.name)")
                }

                Divider()

                Button("New Folder...") {
                    // TODO: Implement new folder
                    print("Create new folder in workflows")
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await workflowService.deleteWorkflow(workflow.id)
                            print("Workflow deleted: \(workflow.name)")
                        } catch {
                            print("Error deleting workflow: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .sectionHeader:
                // No context menu for section headers
                EmptyView()
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

    private func startRename() {
        renamingItemId = item.id
    }

    private func handleRename(newName: String) async throws {
        switch item.itemType {
        case .document(let document):
            let renamedDoc = try await documentService.renameDocument(document.id, newName: newName)
            NSLog("[Sidebar] Document renamed: %@ -> %@", document.name, renamedDoc.name)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Document Renamed"
                alert.informativeText = "\"\\(document.name)\" was successfully renamed to \"\\(renamedDoc.name)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .savedSearch(let search):
            let renamedSearch = try await searchService.renameSavedSearch(search.id, newName: newName)
            NSLog("[Sidebar] Search renamed: %@ -> %@", search.name, renamedSearch.query)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Search Renamed"
                alert.informativeText = "\"\\(search.name)\" was successfully renamed to \"\\(renamedSearch.query)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .conversation(let conversation):
            let renamedConv = try await conversationService.renameConversation(conversation.id, newTitle: newName)
            NSLog("[Sidebar] Conversation renamed: %@ -> %@", conversation.title, renamedConv.title)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Conversation Renamed"
                alert.informativeText = "\"\\(conversation.title)\" was successfully renamed to \"\\(renamedConv.title)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .workflow(let workflow):
            let renamedWorkflow = try await workflowService.renameWorkflow(workflow.id, newName: newName)
            NSLog("[Sidebar] Workflow renamed: %@ -> %@", workflow.name, renamedWorkflow.name)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Workflow Renamed"
                alert.informativeText = "\"\\(workflow.name)\" was successfully renamed to \"\\(renamedWorkflow.name)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .sectionHeader:
            // Cannot rename section headers
            break
        }
    }

    /// Handle drop operation on this item
    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false

        for provider in providers {
            // Handle file URLs (from Finder)
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { (urlData, error) in
                    DispatchQueue.main.async {
                        if let urlData = urlData as? Data,
                           let url = URL(dataRepresentation: urlData, relativeTo: nil) {
                            handleDroppedFile(url: url)
                            handled = true
                        }
                    }
                }
            }
            // Handle document IDs (from sidebar drag)
            else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { (data, error) in
                    DispatchQueue.main.async {
                        if let data = data as? Data,
                           let documentId = String(data: data, encoding: .utf8) {
                            handleDroppedDocument(documentId: documentId)
                            handled = true
                        }
                    }
                }
            }
        }

        return handled
    }

    /// Handle a file dropped from Finder
    private func handleDroppedFile(url: URL) {
        guard case .document(let targetDocument) = item.itemType else {
            NSLog("[Sidebar] Cannot drop file on non-document item")
            return
        }

        // Check if target is a collection or folder (can contain items)
        if targetDocument.docType == .collection || targetDocument.docType == .folder {
            NSLog("[Sidebar] File dropped on \(targetDocument.name): \(url.path)")
            
            Task {
                do {
                    let importedDoc = try await documentStore.importFile(at: url, parentId: targetDocument.id)
                    NSLog("[Sidebar] Successfully imported file: \(importedDoc.name)")
                    
                    // Show success alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "File Imported"
                        alert.informativeText = "\"\(importedDoc.name)\" was successfully imported into \"\(targetDocument.name)\"."
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                } catch {
                    NSLog("[Sidebar] Error importing file: \(error)")
                    
                    // Show error alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "Import Failed"
                        alert.informativeText = "Failed to import file: \(error.localizedDescription)"
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                }
            }
        } else {
            NSLog("[Sidebar] Cannot drop file on document \(targetDocument.name) - not a container")
        }
    }

    /// Handle a document dropped from sidebar (reorganization)
    private func handleDroppedDocument(documentId: String) {
        guard case .document(let targetDocument) = item.itemType else {
            NSLog("[Sidebar] Cannot drop document on non-document item")
            return
        }

        // Prevent dropping on itself
        if documentId == targetDocument.id {
            NSLog("[Sidebar] Cannot drop document on itself")
            return
        }

        // Check if target is a collection or folder (can contain items)
        if targetDocument.docType == .collection || targetDocument.docType == .folder {
            NSLog("[Sidebar] Document \(documentId) dropped on \(targetDocument.name)")
            
            Task {
                do {
                    let movedDoc = try await documentStore.moveDocument(documentId, toParent: targetDocument.id)
                    NSLog("[Sidebar] Successfully moved document: \(movedDoc.name)")
                    
                    // Show success alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "Document Moved"
                        alert.informativeText = "\"\(movedDoc.name)\" was successfully moved into \"\(targetDocument.name)\"."
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                } catch {
                    NSLog("[Sidebar] Error moving document: \(error)")
                    
                    // Show error alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "Move Failed"
                        alert.informativeText = "Failed to move document: \(error.localizedDescription)"
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                }
            }
        } else {
            NSLog("[Sidebar] Cannot drop document on \(targetDocument.name) - not a container")
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
