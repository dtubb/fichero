import SwiftUI
import UniformTypeIdentifiers
import AppKit
import Combine

/// Simple, SwiftUI-native sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    // MARK: - Bindings from parent
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    // MARK: - Data from parent (computed properties in ContentView)
    let libraryItems: [SidebarItem]
    let searchItems: [SidebarItem] 
    let chatItems: [SidebarItem]
    let workflowItems: [SidebarItem]
    
    // MARK: - Environment objects
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var documentService: DocumentService
    @EnvironmentObject var searchService: SavedSearchService
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var workflowService: WorkflowService
    @EnvironmentObject var errorService: ErrorService
    
    // MARK: - Callback
    var onCreateChatWithDocuments: (([String]) -> Void)?
    
    // MARK: - Local state
    @State private var expandedSections: Set<SidebarSection> = [.library, .searches, .chat, .workflows]
    @State private var isChatDropTargeted = false
    @State private var isLibraryDropTargeted = false
    @State private var showingNewFolderDialog = false
    @State private var newFolderName = ""
    @State private var newFolderError: String?
    @State private var isCreatingFolder = false
    @State private var newFolderSection: SidebarSection?
    @State private var newFolderParentId: String?
    
    var body: some View {
        List(selection: $selectedItem) {
            // LIBRARY section
            librarySection
            
            // SEARCHES section  
            searchesSection
            
            // CHAT section
            chatSection
            
            // WORKFLOWS section
            workflowsSection
        }
        .listStyle(.sidebar)
        .frame(minWidth: 200, idealWidth: 240)
        .onChange(of: selectedItem) { _, newItem in
            handleSelection(newItem)
        }
        .onReceive(documentStore.documentChangePublisher.catch { _ in
            Empty(completeImmediately: true)
        }.receive(on: DispatchQueue.main)) { change in
            handleDocumentChange(change)
        }
        .sheet(isPresented: $showingNewFolderDialog) {
            newFolderDialog
        }
    }
    
    // MARK: - Sections
    
    @ViewBuilder
    private var librarySection: some View {
        Section(isExpanded: Binding(
            get: { expandedSections.contains(.library) },
            set: { isExpanded in
                if isExpanded {
                    expandedSections.insert(.library)
                } else {
                    expandedSections.remove(.library)
                }
            }
        )) {
            ForEach(libraryItems) { item in
                SidebarItemRow(
                    item: item,
                    section: .library,
                    viewMode: $viewMode,
                    selectedItem: $selectedItem
                )
                .tag(item)
            }
        } header: {
            SectionHeader(title: "Library", icon: "folder")
        }
        .onDrop(of: [.fileURL], isTargeted: $isLibraryDropTargeted) { providers -> Bool in
            handleLibraryDrop(providers: providers)
        }
    }
    
    @ViewBuilder  
    private var searchesSection: some View {
        Section(isExpanded: Binding(
            get: { expandedSections.contains(.searches) },
            set: { isExpanded in
                if isExpanded {
                    expandedSections.insert(.searches)
                } else {
                    expandedSections.remove(.searches)
                }
            }
        )) {
            ForEach(searchItems) { item in
                SidebarItemRow(
                    item: item,
                    section: .searches,
                    viewMode: $viewMode,
                    selectedItem: $selectedItem
                )
                .tag(item)
            }
            
            // New Search button
            Button(action: createNewSearch) {
                Label("New Search...", systemImage: "plus")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        } header: {
            SectionHeader(title: "Searches", icon: "magnifyingglass")
        }
    }
    
    @ViewBuilder
    private var chatSection: some View {
        Section(isExpanded: Binding(
            get: { expandedSections.contains(.chat) },
            set: { isExpanded in
                if isExpanded {
                    expandedSections.insert(.chat)
                } else {
                    expandedSections.remove(.chat)
                }
            }
        )) {
            ForEach(chatItems) { item in
                SidebarItemRow(
                    item: item,
                    section: .chat,
                    viewMode: $viewMode,
                    selectedItem: $selectedItem
                )
                .tag(item)
            }
            
            // New Chat button with drop support
            newChatButton
        } header: {
            SectionHeader(title: "Chat", icon: "bubble.left.and.bubble.right")
        }
    }
    
    @ViewBuilder
    private var workflowsSection: some View {
        Section(isExpanded: Binding(
            get: { expandedSections.contains(.workflows) },
            set: { isExpanded in
                if isExpanded {
                    expandedSections.insert(.workflows)
                } else {
                    expandedSections.remove(.workflows)
                }
            }
        )) {
            ForEach(workflowItems) { item in
                SidebarItemRow(
                    item: item,
                    section: .workflows,
                    viewMode: $viewMode,
                    selectedItem: $selectedItem
                )
                .tag(item)
            }
            
            // New Workflow button
            Button(action: createNewWorkflow) {
                Label("New Workflow...", systemImage: "plus")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        } header: {
            SectionHeader(title: "Workflows", icon: "arrow.triangle.branch")
        }
    }
    
    @ViewBuilder
    private var newChatButton: some View {
        Button(action: createNewChat) {
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
    }
    
    @ViewBuilder
    private var newFolderDialog: some View {
        VStack(spacing: 16) {
            Text("New Folder")
                .font(.headline)
            
            TextField("Enter folder name", text: $newFolderName)
                .textFieldStyle(.roundedBorder)
                .disableAutocorrection(true)
            
            if let newFolderError = newFolderError {
                Text(newFolderError)
                    .font(.caption)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            
            HStack {
                Button("Cancel") {
                    showingNewFolderDialog = false
                    newFolderName = ""
                    newFolderError = nil
                }
                .keyboardShortcut(.cancelAction)
                
                Spacer()
                
                Button("Create") {
                    Task { await createNewFolder() }
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
    
    private func handleDocumentChange(_ change: DocumentChange) {
        // Handle document changes - view will automatically update since libraryItems
        // is passed from parent and will be recomputed when documentStore changes
        switch change {
        case .collectionsUpdated:
            // Collections updated - parent will recompute libraryItems
            break
        case .collectionSelected(let collection):
            // Auto-select the collection if it exists in our items
            if let item = libraryItems.first(where: { $0.id == collection.id }) {
                selectedItem = item
            }
        case .documentsUpdated, .documentDeleted, .documentCreated:
            // Document changes - parent will handle refresh
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
            provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                    DispatchQueue.main.async {
                        documentIds.append(docId)
                        if documentIds.count == providers.count {
                            self.createNewChatWithDocuments(documentIds)
                        }
                    }
                }
            }
        }
        return true
    }
    
    private func createNewChatWithDocuments(_ documentIds: [String]) {
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }
    
    private func handleLibraryDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { (urlData, _) in
                DispatchQueue.main.async {
                    if let urlData = urlData as? Data,
                       let url = URL(dataRepresentation: urlData, relativeTo: nil) {
                        self.importFile(url: url)
                    }
                }
            }
        }
        return true
    }
    
    private func importFile(url: URL) {
        Task {
            do {
                let importedDoc = try await documentService.importFile(at: url, parentId: nil)
                print("[Sidebar] Imported file: \(importedDoc.name)")
                
                // Show success feedback
                if let window = NSApp.keyWindow {
                    let alert = NSAlert()
                    alert.messageText = "File Imported"
                    alert.informativeText = "\"\\{importedDoc.name}\" was successfully imported."
                    alert.addButton(withTitle: "OK")
                    alert.beginSheetModal(for: window, completionHandler: nil)
                }
            } catch {
                errorService.reportError(ErrorModel.fileSystemError(
                    message: "Failed to import file: \\{error.localizedDescription)",
                    context: ["operation": "file_import", "file_path": url.path],
                    isRecoverable: true
                ))
            }
        }
    }
    
    private func createNewFolder() async {
        guard let section = newFolderSection else {
            newFolderError = "No section specified"
            return
        }
        
        guard !newFolderName.isEmpty else {
            newFolderError = "Folder name cannot be empty"
            return
        }
        
        isCreatingFolder = true
        newFolderError = nil
        
        do {
            let newFolder = try await documentService.createFolder(
                name: newFolderName,
                parentId: newFolderParentId
            )
            
            showingNewFolderDialog = false
            newFolderName = ""
            newFolderParentId = nil
            newFolderSection = nil
            
            // Show success feedback
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Folder Created"
                alert.informativeText = "\"\\{newFolder.name}\" was successfully created."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }
        } catch {
            newFolderError = "Failed to create folder: \\{error.localizedDescription)"
            errorService.reportError(ErrorModel.fileSystemError(
                message: "Failed to create folder",
                context: ["operation": "create_folder", "error": error.localizedDescription],
                isRecoverable: true
            ))
        }
        
        isCreatingFolder = false
    }
}

// Preview
struct SidebarView_Previews: PreviewProvider {
    static var previews: some View {
        SidebarView(
            viewMode: .constant(.library(nil)),
            selectedItem: .constant(nil),
            libraryItems: [
                SidebarItem(id: "1", name: "Documents", icon: "doc", section: .library, itemType: .sectionHeader)
            ],
            searchItems: [],
            chatItems: [],
            workflowItems: []
        )
        .frame(width: 250, height: 400)
    }
}