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
    @EnvironmentObject private var documentService: DocumentService
    @EnvironmentObject private var errorService: ErrorService

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
    @State private var renamingItemId: String?

    // New folder state
    @State private var showingNewFolderDialog = false
    @State private var newFolderParentId: String?
    @State private var newFolderSection: SidebarSection?
    @State private var newFolderName = ""
    @State private var newFolderErrorMessage: String?
    @State private var isCreatingFolder = false
    
    // Inline folder creation state
    @State private var creatingFolderInlineId: String?

    var body: some View {
        List(selection: $selectedItem) {
            // LIBRARY section
            Section(isExpanded: $libraryExpanded) {
                ForEach(libraryItems) { item in
                    SidebarItemRow(
                        item: item,
                        section: .library,
                        expandedItems: $expandedItems,
                        renamingItemId: $renamingItemId,
                        creatingFolderInlineId: $creatingFolderInlineId,
                        showingNewFolderDialog: $showingNewFolderDialog,
                        newFolderParentId: $newFolderParentId,
                        newFolderSection: $newFolderSection,
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
                        section: .searches,
                        expandedItems: $expandedItems,
                        renamingItemId: $renamingItemId,
                        creatingFolderInlineId: $creatingFolderInlineId,
                        showingNewFolderDialog: $showingNewFolderDialog,
                        newFolderParentId: $newFolderParentId,
                        newFolderSection: $newFolderSection,
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
                        section: .chat,
                        expandedItems: $expandedItems,
                        renamingItemId: $renamingItemId,
                        creatingFolderInlineId: $creatingFolderInlineId,
                        showingNewFolderDialog: $showingNewFolderDialog,
                        newFolderParentId: $newFolderParentId,
                        newFolderSection: $newFolderSection,
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
                        section: .workflows,
                        expandedItems: $expandedItems,
                        renamingItemId: $renamingItemId,
                        creatingFolderInlineId: $creatingFolderInlineId,
                        showingNewFolderDialog: $showingNewFolderDialog,
                        newFolderParentId: $newFolderParentId,
                        newFolderSection: $newFolderSection,
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
        .onReceive(documentStore.documentChangePublisher.catch { _ in
            Empty(completeImmediately: true)
        }.receive(on: DispatchQueue.main)) { change in
            handleDocumentChange(change)
        }
        .sheet(isPresented: $showingNewFolderDialog) {
            VStack(spacing: 16) {
                // Title
                Text("New Folder")
                    .font(.headline)

                // Text field
                TextField("Enter folder name", text: Binding(
                    get: { newFolderName },
                    set: { newFolderName = $0 }
                ))
                .textFieldStyle(.roundedBorder)
                .disableAutocorrection(true)

                // Error message
                if let errorMessage = newFolderErrorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                // Buttons
                HStack {
                    Button("Cancel") {
                        showingNewFolderDialog = false
                        newFolderName = ""
                        newFolderErrorMessage = nil
                    }
                    .keyboardShortcut(.cancelAction)

                    Spacer()

                    Button("Create") {
                        Task {
                            await createNewFolderInline()
                        }
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(newFolderName.isEmpty || isCreatingFolder)
                    .overlay {
                        if isCreatingFolder {
                            ProgressView()
                                .scaleEffect(0.7)
                        }
                    }
                }
            }
            .padding()
            .frame(width: 300)
        }
    }

    // MARK: - Actions

    /// Handle document change events from the publisher
    private func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            // Update handled by parent view recomputing libraryItems
            break

        case .collectionSelected(let collection):
            // Update selection if the selected collection is in our library items
            if let item = libraryItems.first(where: { $0.id == collection.id }) {
                selectedItem = item
            }

        case .documentsUpdated:
            // Update handled by parent view
            break

        case .documentDeleted:
            // Remove deleted document from UI
            // Note: The parent view will recompute libraryItems, but we can also handle it here
            // for immediate feedback
            break
        case .documentCreated:
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

    /// Create a new folder in the specified section
    private func createNewFolder(name: String) async throws {
        guard let section = newFolderSection else {
            throw NSError(domain: "com.fichero.sidebar",
                         code: 1,
                         userInfo: [NSLocalizedDescriptionKey: "No section specified for folder creation"])
        }

        // Create the folder using the appropriate service based on section
        let newFolder: Document
        switch section {
        case .library:
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .searches:
            // For searches, we'll create a folder in the searches section
            // This might need a different approach depending on how searches are organized
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .chat:
            // For chat, we'll create a folder in the conversations section
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .workflows:
            // For workflows, we'll create a folder in the workflows section
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        }

        // Show success alert
        if let window = NSApp.keyWindow {
            let alert = NSAlert()
            alert.messageText = "Folder Created"
            alert.informativeText = "\"\(newFolder.name)\" was successfully created."
            alert.addButton(withTitle: "OK")
            alert.beginSheetModal(for: window, completionHandler: nil)
        }

        // Reset state
        newFolderParentId = nil
        newFolderSection = nil
    }

    /// Create a new folder inline (for the sheet dialog)
    private func createNewFolderInline() async {
        guard let section = newFolderSection else {
            let error = ErrorModel.validationError(
                message: "No section specified for folder creation",
                context: ["operation": "create_folder"]
            )
            errorService.reportError(error, showUserFeedback: false)
            newFolderErrorMessage = error.message
            return
        }

        guard !newFolderName.isEmpty else {
            let error = ErrorModel.validationError(
                message: "Folder name cannot be empty",
                context: ["operation": "create_folder", "section": section.rawValue]
            )
            errorService.reportError(error, showUserFeedback: false)
            newFolderErrorMessage = error.message
            return
        }

        isCreatingFolder = true
        newFolderErrorMessage = nil

        do {
            try await createNewFolder(name: newFolderName)
            showingNewFolderDialog = false
            newFolderName = ""
        } catch {
            let errorModel = ErrorModel.fileSystemError(
                message: "Failed to create folder: \(error.localizedDescription)",
                context: [
                    "operation": "create_folder",
                    "folder_name": newFolderName,
                    "section": section.rawValue
                ],
                isRecoverable: true
            )
            errorService.reportError(errorModel)
            newFolderErrorMessage = errorModel.message
        }

        isCreatingFolder = false
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
        errorService.logger.info("[SidebarView] Creating new chat with %d documents", documentIds.count)
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }

    /// Handle drop on Library section (create new collection with imported files)
    private func handleLibrarySectionDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false

        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { (urlData, _) in
                DispatchQueue.main.async {
                    if let urlData = urlData as? Data,
                       let url = URL(dataRepresentation: urlData, relativeTo: nil) {
                        self.handleFileDropOnLibrary(url: url)
                        handled = true
                    }
                }
            }
        }

        return handled
    }

    /// Handle file dropped on Library section
    private func handleFileDropOnLibrary(url: URL) {
        NSLog("[Sidebar] File dropped on Library section: %@", url.path)

        // Defer the import operation to avoid layout recursion
        DispatchQueue.main.async {
            Task {
                do {
                    // Import file as a top-level document (no parent)
                    let importedDoc = try await documentStore.importFile(at: url, parentId: nil)
                    errorService.logger.info("[Sidebar] Successfully imported file to library: %@", importedDoc.name)

                    // Show success alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "File Imported"
                        alert.informativeText = "\"\(importedDoc.name)\" was successfully imported to your library."
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                } catch {
                    let errorModel = ErrorModel.fileSystemError(
                        message: "Failed to import file: \\(error.localizedDescription)",
                        context: [
                            "operation": "file_import",
                            "file_path": url.path,
                            "file_name": url.lastPathComponent
                        ],
                        isRecoverable: true
                    )
                    errorService.reportError(errorModel)

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
}

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
